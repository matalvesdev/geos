# SPEC-001 — Core Runtime

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 0 Foundation

## Context / Problem
Everything in GEOS runs somewhere. A common runtime provides configuration, identity, time,
telemetry, and run semantics so domains and agents share one audit trail.

## Goals
- Load `geos.yaml` + defaults with deterministic validation; secret-free.
- Unique IDs (uuid4) and trace/span semantics for every run.
- Telemetry record per run (duration, model, tokens, cost, tools, errors, retries, approvals).
- Zero external dependencies beyond PyYAML.

## Non-goals
- Distributed tracing; multi-process scheduling; authn/authz of humans.

## Requirements
R1.1 `geos.yaml` schema: `company`, `storage`, `knowledge`, `agents`, `automations`, `approvals`,
     `features`. Unknown keys rejected; sensible defaults applied.
R1.2 `Settings` dataclass with `from_file()` and `defaults()`.
R1.3 `Run` + `RunStatus`; `Telemetry` records runs into the `runs` table via repository.
R1.4 Helpers: `new_id()`, `utc_now()`, `slugify()`, `duration_ms()`.

## Interfaces
```
Settings.from_path(path) -> Settings
new_id() -> str          utc_now() -> datetime
Telemetry.start(workflow_id, agent, trace_id) -> RunContext
RunContext.finish(status, error=None, model=None, tokens=None, cost=None)
```

## Data model
`runs(id, workspace_id, workflow_id, agent, trace_id, status, started_at, finished_at,
duration_ms, model, tokens, cost, error)` — SPEC-002 DDL.

## Security
Config holds no secrets. Logs never print env values.

## Failure modes
Bad YAML → clear parse error with line info. Missing optional fields → defaults, never crash.

## Observability
Every run creates one `runs` row; `geos runs list` surfaces them.

## Tests / Acceptance
`test_config.py`: defaults, file override, unknown-key rejection. `test_telemetry.py`: run
record lifecycle, duration computation. CLI `geos doctor` passes on this workspace. DONE = spec +
impl + tests + docs (this file).
