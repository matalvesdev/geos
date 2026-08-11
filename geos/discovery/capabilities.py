"""Capability discovery (SPEC-009 / mandated SPEC-104-105 core). File-marker heuristics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Detection:
    name: str
    capability: str
    confidence: str
    evidence: list[str] = field(default_factory=list)


class CapabilityDetector:
    """Base class with marker helpers. Plugin detectors extend this (SPEC-105)."""

    name = "base"

    def detect(self, root: Path) -> list[Detection]:
        raise NotImplementedError


def _find_manifest(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def _iter_manifests(root: Path, names: tuple[str, ...], max_depth: int = 3) -> list[Path]:
    """All matching manifests up to max_depth (sidecar layouts nest repos/services)."""
    found: dict[str, Path] = {}
    for name in names:
        for path in sorted(root.glob(f"**/{name}")):
            rel = path.relative_to(root)
            if len(rel.parts) <= max_depth:
                found.setdefault(rel.as_posix(), path)
    return list(found.values())


class SpringBootDetector(CapabilityDetector):
    name = "spring-boot"

    def detect(self, root: Path) -> list[Detection]:
        for pom in _iter_manifests(root, ("pom.xml",)):
            if "spring-boot" in pom.read_text(encoding="utf-8", errors="ignore"):
                return [Detection("spring-boot", "backend_framework", "HIGH", [str(pom)])]
        for gradle in _iter_manifests(root, ("build.gradle", "build.gradle.kts")):
            if "org.springframework.boot" in gradle.read_text(encoding="utf-8", errors="ignore"):
                return [Detection("spring-boot", "backend_framework", "HIGH", [str(gradle)])]
        return []


class ReactViteDetector(CapabilityDetector):
    name = "react-vite"

    def detect(self, root: Path) -> list[Detection]:
        for pkg in _iter_manifests(root, ("package.json",)):
            text = pkg.read_text(encoding="utf-8", errors="ignore")
            if '"vite"' in text and '"react"' in text:
                return [Detection("react-vite", "frontend_framework", "HIGH", [str(pkg)])]
            if '"vite"' in text:
                return [Detection("vite", "frontend_framework", "MEDIUM", [str(pkg)])]
        return []


class NodeDetector(CapabilityDetector):
    name = "node"

    def detect(self, root: Path) -> list[Detection]:
        manifests = _iter_manifests(root, ("package.json",))
        if manifests:
            return [Detection("node", "language_runtime", "HIGH", [str(manifests[0])])]
        return []


class JavaDetector(CapabilityDetector):
    name = "java"

    def detect(self, root: Path) -> list[Detection]:
        manifests = _iter_manifests(root, ("pom.xml", "build.gradle", "build.gradle.kts"))
        if manifests:
            return [Detection("java", "language_runtime", "HIGH", [str(manifests[0])])]
        return []


class PythonDetector(CapabilityDetector):
    name = "python"

    def detect(self, root: Path) -> list[Detection]:
        manifests = _iter_manifests(root, ("pyproject.toml", "requirements.txt", "setup.py"))
        if manifests:
            return [Detection("python", "language_runtime", "HIGH", [str(manifests[0])])]
        return []


class PostgresDetector(CapabilityDetector):
    name = "postgres"

    def detect(self, root: Path) -> list[Detection]:
        for name in ("compose.yaml", "docker-compose.yml", "docker-compose.yaml"):
            candidate = root / name
            if candidate.is_file() and "postgres" in candidate.read_text(
                encoding="utf-8", errors="ignore"
            ):
                return [Detection("postgres", "database", "HIGH", [str(candidate)])]
        return []


class FlywayDetector(CapabilityDetector):
    name = "flyway"

    def detect(self, root: Path) -> list[Detection]:
        for candidate in _iter_manifests(root, ("pom.xml", "build.gradle", "build.gradle.kts")):
            if "flyway" in candidate.read_text(encoding="utf-8", errors="ignore"):
                return [Detection("flyway", "migrations", "HIGH", [str(candidate)])]
        migrations = list(root.glob("**/db/migration/*"))
        if migrations:
            return [Detection("flyway-dir", "migrations", "MEDIUM", [str(p) for p in migrations[:3]])]
        return []


class DockerComposeDetector(CapabilityDetector):
    name = "docker-compose"

    def detect(self, root: Path) -> list[Detection]:
        for name in ("compose.yaml", "compose.yml", "docker-compose.yml"):
            candidate = root / name
            if candidate.is_file():
                return [Detection("docker-compose", "containers", "HIGH", [str(candidate)])]
        return []


class GitHubActionsDetector(CapabilityDetector):
    name = "github-actions"

    def detect(self, root: Path) -> list[Detection]:
        workflows = sorted(root.glob(".github/workflows/*.yml")) + sorted(
            root.glob(".github/workflows/*.yaml")
        )
        if workflows:
            return [Detection("github-actions", "ci_cd", "HIGH", [str(p) for p in workflows])]
        return []


class DocsDetector(CapabilityDetector):
    name = "docs"

    def detect(self, root: Path) -> list[Detection]:
        docs = root / "docs"
        if docs.is_dir():
            md = list(docs.rglob("*.md"))
            if md:
                evidence = [str(md[0]), str(md[-1])] if len(md) > 1 else [str(md[0])]
                return [Detection("docs", "documentation", "HIGH", evidence)]
            return [Detection("docs", "documentation", "MEDIUM", [str(docs)])]
        return []


class AdrDetector(CapabilityDetector):
    name = "adr"

    def detect(self, root: Path) -> list[Detection]:
        for name in ("adr", "adrs", "decisions"):
            candidate = root / "docs" / name
            if candidate.is_dir() and list(candidate.glob("*.md")):
                return [Detection("adr", "decision_records", "HIGH", [str(candidate)])]
        return []


class TestDetector(CapabilityDetector):
    name = "tests"

    def detect(self, root: Path) -> list[Detection]:
        patterns = ("**/*Test.java", "**/*.test.ts", "**/*.test.tsx", "**/*_test.py", "**/test_*.py")
        found = [str(p) for pattern in patterns for p in root.glob(pattern)][:5]
        if found:
            return [Detection("tests", "tests", "HIGH", found)]
        return []


class ChangelogDetector(CapabilityDetector):
    name = "changelog"

    def detect(self, root: Path) -> list[Detection]:
        candidate = root / "CHANGELOG.md"
        if candidate.is_file():
            return [Detection("changelog", "changelog", "HIGH", [str(candidate)])]
        return []


class DesignSystemDetector(CapabilityDetector):
    name = "design-system"

    def detect(self, root: Path) -> list[Detection]:
        markers = ["tailwindcss", "@radix-ui", "class-variance-authority"]
        for pkg in _iter_manifests(root, ("package.json",)):
            text = pkg.read_text(encoding="utf-8", errors="ignore")
            found = [m for m in markers if m in text]
            if found:
                confidence = "HIGH" if len(found) >= 2 else "MEDIUM"
                return [Detection("design-system", "design_system", confidence, [str(pkg)])]
        return []


class MarkdownCMSDetector(CapabilityDetector):
    name = "markdown-cms"

    def detect(self, root: Path) -> list[Detection]:
        for name in ("content", "posts", "blog", "articles"):
            candidate = root / name
            if candidate.is_dir():
                md = list(candidate.glob("**/*.md"))
                if md:
                    return [Detection(f"{name}-cms", "cms", "MEDIUM", [str(candidate)])]
        return []


DEFAULT_DETECTORS: list[CapabilityDetector] = [
    SpringBootDetector(), ReactViteDetector(), NodeDetector(), JavaDetector(), PythonDetector(),
    PostgresDetector(), FlywayDetector(), DockerComposeDetector(), GitHubActionsDetector(),
    DocsDetector(), AdrDetector(), TestDetector(), ChangelogDetector(),
    DesignSystemDetector(), MarkdownCMSDetector(),
]


def scan_capabilities(root: str | Path, detectors: list[CapabilityDetector] | None = None) -> list[Detection]:
    root = Path(root)
    results: list[Detection] = []
    for detector in detectors or DEFAULT_DETECTORS:
        try:
            results.extend(detector.detect(root))
        except Exception:  # noqa: BLE001 - a broken detector must not block the scan
            results.append(
                Detection(detector.name, "unknown", "LOW", ["detector raised"])
            )
    return results


def capability_actions() -> dict[str, str]:
    """Recommended GEOS action per capability (brownfield reuse-first, ADR-0005)."""
    return {
        "backend_framework": "REUSE",
        "frontend_framework": "REUSE",
        "language_runtime": "REUSE",
        "database": "REUSE",
        "migrations": "REUSE",
        "containers": "REUSE",
        "ci_cd": "REUSE",
        "documentation": "INTEGRATE",
        "decision_records": "INTEGRATE",
        "tests": "REUSE",
        "changelog": "INTEGRATE",
        "design_system": "REUSE",
        "cms": "INTEGRATE",
        "search": "CREATE",
        "knowledge": "CREATE",
        "agent_runtime": "CREATE",
        "approvals": "CREATE",
    }
