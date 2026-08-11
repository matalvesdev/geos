"""SPEC-008/009 discovery tests."""

from __future__ import annotations

import unittest

from geos.discovery.capabilities import scan_capabilities
from geos.discovery.mode import BROWNFIELD, GREENFIELD, STANDALONE, discover_mode
from tests.helpers import TempDir


class ModeDetectionTests(unittest.TestCase):
    def test_empty_dir_is_greenfield(self) -> None:
        with TempDir() as tmp:
            result = discover_mode(tmp)
        self.assertEqual(result.mode, GREENFIELD)

    def test_source_code_is_brownfield_high(self) -> None:
        with TempDir() as tmp:
            (tmp / "services" / "api").mkdir(parents=True)
            (tmp / "services" / "api" / "Main.java").write_text("class Main {}", encoding="utf-8")
            for i in range(6):
                (tmp / "services" / "api" / f"File{i}.java").write_text("class F {}", encoding="utf-8")
            (tmp / "pom.xml").write_text("<project></project>", encoding="utf-8")
            (tmp / ".github" / "workflows").mkdir(parents=True)
            (tmp / ".github" / "workflows" / "ci.yml").write_text("jobs: {}", encoding="utf-8")
            result = discover_mode(tmp)
        self.assertEqual(result.mode, BROWNFIELD)
        self.assertEqual(result.confidence, "HIGH")
        self.assertTrue(result.evidence)

    def test_standalone_marker(self) -> None:
        with TempDir() as tmp:
            (tmp / ".geos").mkdir()
            (tmp / ".geos" / "standalone.json").write_text("{}", encoding="utf-8")
            result = discover_mode(tmp)
        self.assertEqual(result.mode, STANDALONE)
        self.assertEqual(result.confidence, "HIGH")

    def test_config_declares_repositories_standalone(self) -> None:
        with TempDir() as tmp:
            (tmp / "geos.yaml").write_text(
                "repositories:\n  - id: a\n    path: ../a\n", encoding="utf-8"
            )
            result = discover_mode(tmp)
        self.assertEqual(result.mode, STANDALONE)

    def test_explicit_mode_override(self) -> None:
        with TempDir() as tmp:
            result = discover_mode(tmp)
        self.assertEqual(result.mode, GREENFIELD)


class CapabilityTests(unittest.TestCase):
    def test_spring_boot_detected(self) -> None:
        with TempDir() as tmp:
            (tmp / "pom.xml").write_text(
                "<project><dependencies><dependency>spring-boot-starter-web</dependency>"
                "</dependencies></project>",
                encoding="utf-8",
            )
            detections = scan_capabilities(tmp)
        names = {d.name for d in detections}
        self.assertIn("spring-boot", names)
        spring = next(d for d in detections if d.name == "spring-boot")
        self.assertEqual(spring.capability, "backend_framework")

    def test_react_vite_detected(self) -> None:
        with TempDir() as tmp:
            (tmp / "package.json").write_text(
                '{"dependencies": {"react": "^19", "vite": "^7"}}', encoding="utf-8"
            )
            detections = scan_capabilities(tmp)
        self.assertIn("react-vite", {d.name for d in detections})

    def test_no_false_positive_empty_dir(self) -> None:
        with TempDir() as tmp:
            detections = scan_capabilities(tmp)
        self.assertEqual(detections, [])

    def test_github_actions_and_compose(self) -> None:
        with TempDir() as tmp:
            (tmp / ".github" / "workflows").mkdir(parents=True)
            (tmp / ".github" / "workflows" / "ci.yml").write_text("", encoding="utf-8")
            (tmp / "compose.yaml").write_text("services:\n  postgres:\n    image: postgres:17\n",
                                             encoding="utf-8")
            detections = scan_capabilities(tmp)
        names = {d.name for d in detections}
        self.assertIn("github-actions", names)
        self.assertIn("postgres", names)
        self.assertIn("docker-compose", names)


if __name__ == "__main__":
    unittest.main()
