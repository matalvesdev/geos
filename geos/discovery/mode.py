"""Project discovery & mode detection (SPEC-008 / mandated SPEC-101-102). Deterministic heuristics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

GREENFIELD = "GREENFIELD"
BROWNFIELD = "BROWNFIELD"
STANDALONE = "STANDALONE"

_SOURCE_DIRS = {
    "services", "src", "packages", "app", "backend", "frontend", "server", "api",
    "lib", "libs", "cmd", "internal", "modules",
}
_PACKAGE_MANIFESTS = {
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts", "Cargo.toml",
    "go.mod", "requirements.txt", "pyproject.toml", "setup.py", "composer.json",
    "Gemfile", "mix.exs", "pubspec.yaml",
}
_SOURCE_EXTENSIONS = {".java", ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".kt", ".cs", ".rb"}
_TEST_PATTERNS = (
    "**/*.test.ts", "**/*.test.tsx", "**/*.test.js", "**/*.test.jsx",
    "**/*.spec.ts", "**/*Test.java", "**/*Tests.java",
    "**/test_*.py", "**/*_test.py",
)
_DOT_DIRS = {".git", ".geos", ".pnpm-store", ".playwright-cli", ".venv", "node_modules", "dist", "build"}


@dataclass
class ModeResult:
    mode: str
    confidence: str  # HIGH | MEDIUM | LOW
    evidence: list[str] = field(default_factory=list)
    detected_by: str = "heuristics"

    def is_high(self) -> bool:
        return self.confidence == "HIGH"


def discover_mode(root: str | Path) -> ModeResult:
    """Detect the installation scenario. Read-only, never executes anything."""
    root = Path(root)
    evidence: list[str] = []
    signals = 0

    # STANDALONE: explicit control-plane markers.
    standalone_markers = [
        root / "workspace.yaml",
        root / ".geos" / "standalone.json",
    ]
    for marker in standalone_markers:
        if marker.is_file():
            evidence.append(f"STANDALONE marker found: {marker}")
            return ModeResult(
                STANDALONE, "HIGH",
                ["standalone control-plane marker"] + evidence, detected_by="marker",
            )
    geos_yaml = root / "geos.yaml"
    if geos_yaml.is_file():
        from ..config import Settings

        try:
            settings = Settings.from_path(geos_yaml, root=root)
            if settings.repositories:
                evidence.append(f"geos.yaml declares {len(settings.repositories)} repositories")
                return ModeResult(
                    STANDALONE, "HIGH", evidence, detected_by="config-repositories",
                )
        except Exception:
            pass

    # BROWNFIELD signals (root-level and one level deep — sidecar layouts nest the repo).
    source_dirs = _find_source_dirs(root)
    if source_dirs:
        signals += 1
        evidence.append(f"source directories: {', '.join(sorted(source_dirs))}")
    manifests = _find_manifests(root)
    if manifests:
        signals += 1
        evidence.append(f"package manifests: {', '.join(sorted(manifests))}")
    source_files = _count_source_files(root, depth=6)
    if source_files >= 5:
        signals += 1
        evidence.append(f"{source_files} source files detected")
    ci_dirs = list(root.glob(".github/workflows/*")) or list(root.glob(".gitlab-ci.yml"))
    if ci_dirs:
        signals += 1
        evidence.append("CI/CD configuration detected")
    test_files = _count_test_files(root)
    if test_files > 0:
        signals += 1
        evidence.append(f"{test_files} test files detected")

    if signals >= 3:
        return ModeResult(BROWNFIELD, "HIGH", evidence)
    if signals == 2:
        return ModeResult(BROWNFIELD, "MEDIUM", evidence)
    if signals == 1:
        return ModeResult(BROWNFIELD, "LOW", evidence)

    evidence.append("no meaningful source code detected")
    return ModeResult(GREENFIELD, "HIGH" if not evidence else "MEDIUM", evidence)


def _find_source_dirs(root: Path) -> list[str]:
    found: set[str] = set()
    for child in root.iterdir():
        if child.is_dir() and child.name not in _DOT_DIRS:
            if child.name in _SOURCE_DIRS:
                found.add(child.name)
            for grandchild in child.iterdir():
                if grandchild.is_dir() and grandchild.name in _SOURCE_DIRS:
                    found.add(f"{child.name}/{grandchild.name}")
    return sorted(found)


def _find_manifests(root: Path) -> list[str]:
    found: set[str] = set()
    for child in root.iterdir():
        if child.is_file() and child.name in _PACKAGE_MANIFESTS:
            found.add(child.name)
        elif child.is_dir() and child.name not in _DOT_DIRS:
            for grandchild in child.iterdir():
                if grandchild.is_file() and grandchild.name in _PACKAGE_MANIFESTS:
                    found.add(f"{child.name}/{grandchild.name}")
    return sorted(found)


def _count_test_files(root: Path) -> int:
    total = 0
    for pattern in _TEST_PATTERNS:
        for path in root.glob(pattern):
            if not any(part in _DOT_DIRS for part in path.parts):
                total += 1
    return total


def _count_source_files(root: Path, depth: int = 6) -> int:
    count = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in _SOURCE_EXTENSIONS:
            if any(part in _DOT_DIRS for part in path.parts):
                continue
            rel_depth = len(path.relative_to(root).parts)
            if rel_depth <= depth:
                count += 1
    return count
