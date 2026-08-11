# SPEC-008 — Project Discovery & Mode Detection

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Adoption foundation · ADR-0004/0005 · Covers mandated SPEC-101/102

## Context / Problem
`geos init` must never assume an empty repo or an existing codebase. It must detect the scenario
(GREENFIELD / BROWNFIELD / STANDALONE) with deterministic heuristics, report evidence and
confidence, and never block execution unnecessarily.

## Goals
- Deterministic mode detection from filesystem signals (no LLM).
- Evidence list + confidence (HIGH/MEDIUM/LOW) in output and persisted manifest.
- `--mode` override for explicit selection.
- Minimal footprint: writes only `.geos/` and `docs/geos/` (never product files).

## Non-goals
- Deep static analysis (later capability discovery, SPEC-009); content assessment.

## Requirements (heuristics, in priority order)
R8.1 STANDALONE if a GEOS `workspace.yaml`/`repositories:` config exists or marker
     `.geos/standalone.json`; also if `geos.yaml` declares `repositories`.
R8.2 BROWNFIELD if meaningful source code exists: source dirs (`services/`, `src/`, `packages/`,
     `app/`, `backend/`, `frontend/`, `server/`, `api/`), package manifests (`package.json`,
     `pom.xml`, `build.gradle`, `Cargo.toml`, `requirements.txt`, `pyproject.toml`, `go.mod`),
     more than N source files, or git history with code.
R8.3 GREENFIELD otherwise (no meaningful source code).
R8.4 Confidence: HIGH when several independent signals agree; MEDIUM on ambiguity; LOW when
     signals conflict (report and proceed with best judgment, recorded).
R8.5 Every detection result is stored in `.geos/project-manifest.json` with `mode`, `confidence`,
     `evidence[]`.

## Interfaces
```
discover_mode(root) -> ModeResult(mode, confidence, evidence)
write_manifest(root, manifest) -> path
```

## Security
Read-only inspection. No execution of detected files.

## Failure modes
Unreadable dir → skipped with warning; total failure → GREENFIELD fallback with LOW confidence,
never crash.

## Tests / Acceptance
`test_discovery.py`: empty dir → GREENFIELD HIGH; dir with `package.json`+`src/` → BROWNFIELD
HIGH; dir with `workspace.yaml` repositories → STANDALONE HIGH; ambiguity → MEDIUM.
CLI: `geos init` on this workspace detects BROWNFIELD and writes manifest.
