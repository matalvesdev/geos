"""Spec §46–§47 policy classification tests."""

from __future__ import annotations

import unittest

from geos.core.policies import RiskLevel, classify_action


class PolicyTests(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(classify_action("research.run"), RiskLevel.SAFE_AUTOMATIC)
        self.assertEqual(classify_action("content.draft"), RiskLevel.SAFE_AUTOMATIC)
        self.assertEqual(classify_action("blog.publish"), RiskLevel.HUMAN_APPROVAL_REQUIRED)
        self.assertEqual(classify_action("social.publish"), RiskLevel.HUMAN_APPROVAL_REQUIRED)
        self.assertEqual(classify_action("meeting.invite"), RiskLevel.HUMAN_APPROVAL_REQUIRED)

    def test_unknown_action_review_recommended(self) -> None:
        self.assertEqual(classify_action("brand.new.action"), RiskLevel.REVIEW_RECOMMENDED)

    def test_prohibited(self) -> None:
        self.assertEqual(
            classify_action("social.engage_automated"), RiskLevel.PROHIBITED_AUTOMATION
        )

    def test_config_override(self) -> None:
        overrides = {"blog.publish": "SAFE_AUTOMATIC"}
        self.assertEqual(
            classify_action("blog.publish", overrides), RiskLevel.SAFE_AUTOMATIC
        )


if __name__ == "__main__":
    unittest.main()
