"""SPEC-006 cron parser tests (deterministic, dependency-free)."""

from __future__ import annotations

import unittest
from datetime import datetime

from geos.core.scheduler import CronExpr, CronSyntaxError


class CronTests(unittest.TestCase):
    def test_every_minute(self) -> None:
        cron = CronExpr.parse("* * * * *")
        self.assertTrue(cron.matches(datetime(2026, 8, 11, 9, 30)))

    def test_specific(self) -> None:
        cron = CronExpr.parse("30 9 11 8 *")
        self.assertTrue(cron.matches(datetime(2026, 8, 11, 9, 30)))
        self.assertFalse(cron.matches(datetime(2026, 8, 11, 9, 31)))
        self.assertFalse(cron.matches(datetime(2026, 8, 10, 9, 30)))

    def test_step(self) -> None:
        cron = CronExpr.parse("*/15 * * * *")
        self.assertTrue(cron.matches(datetime(2026, 8, 11, 9, 0)))
        self.assertTrue(cron.matches(datetime(2026, 8, 11, 9, 15)))
        self.assertFalse(cron.matches(datetime(2026, 8, 11, 9, 10)))

    def test_range_and_list(self) -> None:
        cron = CronExpr.parse("0 9-17 * * 1-5")
        self.assertTrue(cron.matches(datetime(2026, 8, 11, 14, 0)))  # Tue
        self.assertFalse(cron.matches(datetime(2026, 8, 11, 18, 0)))
        self.assertFalse(cron.matches(datetime(2026, 8, 15, 10, 0)))  # Sat

    def test_dow_sunday(self) -> None:
        cron = CronExpr.parse("0 0 * * 0")
        self.assertTrue(cron.matches(datetime(2026, 8, 16, 0, 0)))  # Sunday
        self.assertFalse(cron.matches(datetime(2026, 8, 15, 0, 0)))  # Saturday

    def test_dow_sunday_does_not_match_other_days(self) -> None:
        # Regression: Sunday must NOT match a dow set that excludes 0/7.
        monday_only = CronExpr.parse("0 0 * * 1")
        self.assertFalse(monday_only.matches(datetime(2026, 8, 16, 0, 0)))  # Sunday
        self.assertTrue(monday_only.matches(datetime(2026, 8, 17, 0, 0)))  # Monday
        sunday7 = CronExpr.parse("0 0 * * 7")  # 7 normalizes to Sunday
        self.assertTrue(sunday7.matches(datetime(2026, 8, 16, 0, 0)))

    def test_next_after(self) -> None:
        cron = CronExpr.parse("0 9 * * *")
        nxt = cron.next_after(datetime(2026, 8, 11, 9, 0))
        self.assertEqual(nxt, datetime(2026, 8, 12, 9, 0))
        nxt2 = cron.next_after(datetime(2026, 8, 11, 9, 0, 30))
        self.assertEqual(nxt2, datetime(2026, 8, 12, 9, 0))

    def test_invalid_expressions(self) -> None:
        for bad in ("* * * *", "60 * * * *", "a * * * *", "1-7-9 * * * *", "*/0 * * * *"):
            with self.assertRaises(CronSyntaxError, msg=bad):
                CronExpr.parse(bad)

    def test_question_mark(self) -> None:
        cron = CronExpr.parse("0 9 ? * 1")  # '?' == '*' (numeric day-of-week)
        self.assertEqual(cron.dow, frozenset({1}))

    def test_day_names_rejected(self) -> None:
        with self.assertRaises(CronSyntaxError):
            CronExpr.parse("0 9 ? * MON")


if __name__ == "__main__":
    unittest.main()
