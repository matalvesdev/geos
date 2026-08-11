"""CLI end-to-end tests (init/doctor/migrate/knowledge/workflows) in temp workspaces."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import TempDir

GEO = Path(__file__).resolve().parents[1]
GEO_PKG = GEO  # parent of `geos` package dir


def run_cli(root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(GEO)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "geos.cli", "--root", str(root), *argv],
        capture_output=True, text=True, env=env, cwd=str(GEO),
    )


class CliTests(unittest.TestCase):
    def test_init_greenfield(self) -> None:
        with TempDir() as tmp:
            proc = run_cli(tmp, "init")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("GREENFIELD", proc.stdout)
            self.assertTrue((tmp / ".geos" / "geos.yaml").is_file())
            self.assertTrue((tmp / ".geos" / "project-manifest.json").is_file())

    def test_init_brownfield_detection(self) -> None:
        with TempDir() as tmp:
            (tmp / "services" / "api").mkdir(parents=True)
            for i in range(6):
                (tmp / "services" / "api" / f"F{i}.java").write_text("class F {}", encoding="utf-8")
            (tmp / "pom.xml").write_text("<project/>", encoding="utf-8")
            proc = run_cli(tmp, "init")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("BROWNFIELD", proc.stdout)
            manifest = (tmp / ".geos" / "project-manifest.json").read_text(encoding="utf-8")
            self.assertIn("BROWNFIELD", manifest)

    def test_init_mode_override_and_repo_seed(self) -> None:
        with TempDir() as tmp:
            (tmp / "zetra-one").mkdir()
            proc = run_cli(tmp, "init", "--mode", "brownfield")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            registry = (tmp / ".geos" / "repositories.json").read_text(encoding="utf-8")
            self.assertIn("zetra-one", registry)

    def test_doctor_ok(self) -> None:
        with TempDir() as tmp:
            proc = run_cli(tmp, "doctor")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("ALL CHECKS PASSED", proc.stdout)

    def test_db_migrate(self) -> None:
        with TempDir() as tmp:
            proc = run_cli(tmp, "db", "migrate")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Schema version", proc.stdout)

    def test_knowledge_ingest_search_cli(self) -> None:
        with TempDir() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            (docs / "guide.md").write_text(
                "# Guia\n\nO fluxo de origem de crédito é essencial para a decisão financeira.\n",
                encoding="utf-8",
            )
            run_cli(tmp, "db", "migrate")
            ingest = run_cli(tmp, "knowledge", "ingest", str(docs), "--source", "test")
            self.assertEqual(ingest.returncode, 0, ingest.stderr)
            self.assertIn("added=1", ingest.stdout)
            search = run_cli(tmp, "knowledge", "search", "origem de crédito")
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("result", search.stdout)
            self.assertIn("guide.md", search.stdout)

    def test_workflows_list_and_run(self) -> None:
        with TempDir() as tmp:
            # Point config at the shipped example workflows.
            cfg = tmp / ".geos" / "geos.yaml"
            cfg.parent.mkdir()
            cfg.write_text(f"workflows:\n  dir: {GEO / 'workflows'}\n", encoding="utf-8")
            listing = run_cli(tmp, "workflows", "list")
            self.assertEqual(listing.returncode, 0, listing.stderr)
            self.assertIn("content-idea", listing.stdout)
            self.assertIn("daily-intelligence", listing.stdout)

            run = run_cli(tmp, "workflows", "run", "content-idea", "--approve", "publish")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("SUCCESS", run.stdout)

            runs = run_cli(tmp, "runs", "list")
            self.assertEqual(runs.returncode, 0, runs.stderr)
            self.assertIn("content-idea", runs.stdout)

            approvals = run_cli(tmp, "approvals", "list")
            self.assertEqual(approvals.returncode, 0, approvals.stderr)
            self.assertIn("pending", approvals.stdout)

    def test_phase1_cli_commands(self) -> None:
        """graph extract/inspect + research run end-to-end (SPEC-013/021)."""
        with TempDir() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            (docs / "origem.md").write_text(
                "# Origem de crédito\n\nA origem de crédito bancário exige evidência "
                "documental para a decisão financeira. Azeetra e Zetra One endereçam a "
                "conciliação bancária.\n",
                encoding="utf-8",
            )
            self.assertEqual(run_cli(tmp, "db", "migrate").returncode, 0)
            ingest = run_cli(tmp, "knowledge", "ingest", str(docs), "--source", "test")
            self.assertEqual(ingest.returncode, 0, ingest.stderr)
            self.assertIn("embeddings=", ingest.stdout)
            self.assertIn("embeddings=1", ingest.stdout)

            g = run_cli(tmp, "graph", "extract")
            self.assertEqual(g.returncode, 0, g.stderr)
            self.assertIn("nodes=", g.stdout)
            insp = run_cli(tmp, "graph", "inspect", "--type", "TOPIC")
            self.assertEqual(insp.returncode, 0, insp.stderr)
            self.assertIn("TOPIC nodes:", insp.stdout)

            r = run_cli(tmp, "research", "run", "origem de crédito")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("sources (", r.stdout)
            self.assertIn("OBSERVATION", r.stdout)

    def test_plan_experimental(self) -> None:
        with TempDir() as tmp:
            (tmp / "services" / "api").mkdir(parents=True)
            (tmp / "services" / "api" / "A.java").write_text("class A {}", encoding="utf-8")
            (tmp / "pom.xml").write_text(
                "<project><dependencies>spring-boot-starter-web</dependencies></project>",
                encoding="utf-8",
            )
            run_cli(tmp, "init")
            plan = run_cli(tmp, "plan")
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("REUSE", plan.stdout)


if __name__ == "__main__":
    unittest.main()
