# SPEC-009 — Capability Discovery & Project Manifest

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Adoption foundation · Covers mandated SPEC-104 (partial), SPEC-105 (core detectors), SPEC-107 (registry seed)

## Context / Problem
GEOS must know what a connected repository already provides (reuse first, create last) and record
a machine-readable manifest for planning (`geos plan` later).

## Goals
- Deterministic capability detectors (file/marker heuristics) for: backend frameworks, frontend
  frameworks, databases, queues, analytics, CMS, CI/CD, containers, documentation, tests,
  migrations, design system, changelog, ADRs/specs.
- Confidence per detection.
- `.geos/project-manifest.json` summarizing mode, capabilities, repositories, languages.
- Repository Registry: a lightweight registry (JSON + optional SQLite table) with a seeded
  `zetra-one` entry for this workspace.

## Non-goals
- Detector plugin API (SPEC-105 full) — protocol designed, plugin loading later.
- Content quality assessment.

## Requirements
R9.1 `CapabilityDetector` protocol: `detect(root) -> list[Detection(name, capability, confidence,
     evidence)]`.
R9.2 Core detectors: SpringBootDetector (pom.xml + spring-boot), MavenDetector, ReactViteDetector,
     NodeDetector, PostgresComposeDetector, FlywayDetector, DockerComposeDetector, GitHubActionsCI,
     DocsDetector (docs/ + adr/), TestDetector, MigrationsDetector, ChangelogDetector,
     MarkdownCMSDetector, DesignSystemDetector (tailwind/radix/shadcn markers).
R9.3 `scan_capabilities(root)` aggregates; each result carries confidence + evidence paths.
R9.4 Manifest writer: `mode, confidence, capabilities[], repositories[], languages[], last_audit`.
R9.5 Repository Registry: `repo add/list/scan` data in `.geos/repositories.json`; seed
     `zetra-one` on init when detected; per-repo capabilities cached.

## Interfaces
```
detections = scan_capabilities(root)
manifest = build_manifest(root, mode_result, detections, repos)
registry = RepositoryRegistry(db, json_path)   # add/list/get
```

## Security
Read-only; detectors never execute build tools.

## Failure modes
Missing markers → capability absent (not guessed); conflicting markers → both recorded with
confidence.

## Tests / Acceptance
`test_capabilities.py`: synthetic fixture trees for Spring Boot, React/Vite, docs, GitHub Actions;
wrong fixture → no false positive. `test_manifest.py`: manifest round-trip; registry add/list;
seed detects `zetra-one`.
