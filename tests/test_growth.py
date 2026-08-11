"""SPEC-034 opportunity + experiment engine tests."""

from __future__ import annotations

import unittest

from geos.domains.content import ContentEngine
from geos.domains.growth import ExperimentEngine, GrowthError, OpportunityEngine
from geos.domains.seo import SeoEngine
from geos.intelligence.knowledge import ingest_directory
from tests.helpers import TempDir, temp_db


class ScoringTests(unittest.TestCase):
    def test_ice_math(self) -> None:
        from geos.domains.growth import _score_ice

        score, breakdown = _score_ice({"impact": 8, "confidence": 7, "effort": 3})
        # (8 * 7 * 7) / 100 = 3.92
        self.assertAlmostEqual(score, 3.92, places=3)
        self.assertEqual(breakdown["method"], "ice")
        self.assertEqual(breakdown["ease"], 7)
        self.assertIn("formula", breakdown)

    def test_rice_math(self) -> None:
        from geos.domains.growth import _score_rice

        score, breakdown = _score_rice(
            {"reach": 1000, "impact": 2.0, "confidence": 0.9, "effort": 5}
        )
        # (1000 * 2 * 0.9) / 5 = 360
        self.assertAlmostEqual(score, 360.0, places=3)
        self.assertEqual(breakdown["method"], "rice")

    def test_neutral_defaults(self) -> None:
        from geos.domains.growth import _score_ice, _score_rice

        ice, _ = _score_ice({})
        self.assertAlmostEqual(ice, (5 * 5 * 5) / 100, places=3)  # 1.25
        rice, _ = _score_rice({})
        self.assertAlmostEqual(rice, (100 * 1.0 * 0.8) / 1.0, places=3)  # 80.0


class OpportunityEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = OpportunityEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_and_score_ice(self) -> None:
        item = self.engine.create(
            "Conteúdo sobre cash application gera interesse",
            audience="finops", impact=8, confidence=7, effort=3,
        )
        scored = self.engine.score(item["id"], method="ice")
        self.assertEqual(scored["score_method"], "ice")
        self.assertAlmostEqual(scored["score"], 3.92, places=2)
        self.assertIn("impact", scored["breakdown"])

    def test_score_explainable_not_just_number(self) -> None:
        item = self.engine.create("oportunidade qualquer")
        breakdown = self.engine.score(item["id"], method="rice")["breakdown"]
        for key in ("reach", "impact", "confidence", "effort", "formula"):
            self.assertIn(key, breakdown)

    def test_collect_from_research_and_seo_dedup(self) -> None:
        # one research report with an opportunity
        from geos.domains.research import ResearchEngine
        from geos.storage.repos import RepoFactory

        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "a.md").write_text(
                "# Origem de crédito\n\nA origem de crédito bancário é essencial "
                "para decisão financeira.\n", encoding="utf-8")
            ingest_directory(self.db, tmp / "docs", source="test")
        ResearchEngine(self.db).run("origem de crédito")
        # one seo content gap
        RepoFactory(self.db).knowledge.upsert_node(
            "TOPIC", "conciliação bancária", canonical_name="conciliação bancária",
            source="test")

        first = self.engine.collect()
        self.assertGreaterEqual(first["research"], 1)
        self.assertGreaterEqual(first["seo"], 1)
        # idempotent — second collect skips
        second = self.engine.collect()
        self.assertEqual(second["research"], 0)
        self.assertEqual(second["seo"], 0)
        self.assertGreaterEqual(second["skipped"], 1)

    def test_collect_multiple_opportunities_same_report(self) -> None:
        """Regression: dedup per-problem, not per-report (SPEC-034 R2)."""
        from geos.storage.repos import RepoFactory

        repo = RepoFactory(self.db)
        repo.research.insert(
            "r1", "pergunta", "COMPLETED", [], [], [], "síntese", [],
            [
                {"type": "CONTENT_OPPORTUNITY", "content": "Tópico A",
                 "confidence": 0.7},
                {"type": "CONTENT_OPPORTUNITY", "content": "Tópico B",
                 "confidence": 0.6},
            ],
        )
        created = self.engine.collect()
        self.assertEqual(created["research"], 2,
                         "cada oportunidade do relatório deve virar uma opportunity")
        self.assertEqual(created["skipped"], 0)
        # idempotent — second collect skips both
        second = self.engine.collect()
        self.assertEqual(second["research"], 0)
        self.assertEqual(second["skipped"], 2)
        problems = {i["problem"] for i in repo.opportunities.list()}
        self.assertEqual(problems, {"Tópico A", "Tópico B"})

    def test_update_components_invalidates_cached_score(self) -> None:
        """Regression: component change must recompute, not return stale score."""
        item = self.engine.create("oportunidade", impact=8, confidence=7, effort=3)
        self.engine.score(item["id"], method="ice")
        self.assertAlmostEqual(self.engine.get(item["id"])["score"], 3.92, places=2)
        # change a component without re-scoring via score()
        self.engine.update_components(item["id"], impact=10)
        refreshed = self.engine.get(item["id"])
        self.assertIsNone(refreshed["score"], "component change must invalidate score")
        self.assertIsNone(refreshed["score_method"])
        # next list recomputes with the new component
        scored = self.engine.list(method="ice")[0]
        # (10 * 7 * 7) / 100 = 4.9
        self.assertAlmostEqual(scored["score"], 4.9, places=2)

    def test_create_requires_problem(self) -> None:
        with self.assertRaises(GrowthError):
            self.engine.create("   ")

    def test_unknown_method_rejected(self) -> None:
        item = self.engine.create("x")
        with self.assertRaises(GrowthError):
            self.engine.score(item["id"], method="nope")


class ExperimentEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = OpportunityEngine(self.db)
        self.experiments = ExperimentEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_lifecycle_full(self) -> None:
        opp = self.engine.create("oportunidade de teste")
        experiment = self.experiments.from_opportunity(
            opp["id"], primary_metric="conversion_rate")
        self.assertEqual(experiment["status"], "PROPOSED")
        self.assertIn("melhora", experiment["hypothesis"])
        # proposal marks the opportunity
        self.assertEqual(self.engine.get(opp["id"])["status"], "EXPERIMENTING")
        # only from OPEN
        with self.assertRaises(GrowthError):
            self.experiments.from_opportunity(opp["id"], primary_metric="m")
        running = self.experiments.transition(experiment["id"], "RUNNING")
        self.assertEqual(running["status"], "RUNNING")
        # illegal transition
        with self.assertRaises(GrowthError):
            self.experiments.transition(experiment["id"], "PROPOSED")
        done = self.experiments.complete(
            experiment["id"], result="CTA 2x", analysis="amostra pequena",
            decision="ITERATE", learning="repetir com mais tráfego")
        self.assertEqual(done["status"], "COMPLETED")
        self.assertEqual(done["decision"], "ITERATE")

    def test_complete_requires_result_and_learning(self) -> None:
        opp = self.engine.create("x")
        exp = self.experiments.from_opportunity(opp["id"], primary_metric="m")
        self.experiments.transition(exp["id"], "RUNNING")
        with self.assertRaises(GrowthError):
            self.experiments.complete(exp["id"], result="", analysis="",
                                      decision="ADOPT", learning="")
        with self.assertRaises(GrowthError):
            self.experiments.complete(exp["id"], result="r", analysis="",
                                      decision="UNKNOWN", learning="l")

    def test_complete_only_from_running(self) -> None:
        opp = self.engine.create("x")
        exp = self.experiments.from_opportunity(opp["id"], primary_metric="m")
        with self.assertRaises(GrowthError):
            self.experiments.complete(exp["id"], result="r", analysis="",
                                      decision="ADOPT", learning="l")


if __name__ == "__main__":
    unittest.main()
