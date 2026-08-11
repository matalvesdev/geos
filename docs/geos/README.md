# GEOS — Growth, Education & Organizational System

> **State: CURRENT (bootstrap)** · Started: 2026-08-11 · Status: **SPECIFIED / PARTIALLY_IMPLEMENTED**

GEOS is an open-source, local-first, agentic organizational growth platform. It transforms
**market signals → research → knowledge → strategy → content → distribution → leads →
qualification → meetings → opportunities → customers → education → community → analytics →
learning** into a continuous, measurable loop.

This documentation tree follows SDD (Spec-Driven Development). **Nothing is documented as
existing unless it is implemented.** Document states: `CURRENT` · `PROPOSED` · `PLANNED` ·
`EXPERIMENTAL` · `DEPRECATED` · `ARCHIVED`.

## Installation model (this workspace)

| Aspect | Decision | Evidence |
|---|---|---|
| Mode | `BROWNFIELD` (auto-detected) | `zetra-one/` contains canonical product code |
| Installation | `SIDECAR` (`geos/` at workspace root) | No product code is modified |
| First client | Zetra One (`zetra-one/`) | Repository Registry entry `zetra-one` |
| Storage | SQLite, isolated: `.geos/geos.db` | ADR-0002 |

## Documentation map

```
docs/geos/
├── README.md                 ← this file
├── audits/initial-audit.md   ← Rule Zero: full repository audit (KEEP/IMPROVE/…)
├── context/company-context.md← Zetra / Azeetra company discovery
├── architecture/vision.md    ← GEOS architecture vision
├── adrs/GEOS-ADR-0001..0006  ← foundational decisions
├── roadmaps/roadmap.md       ← phased roadmap + mandated adoption specs
├── specs/SPEC-001..010       ← specs implemented in this bootstrap
├── automation/catalog.md     ← automation catalog (L0..L5 maturity)
└── state/                    ← (populated by `geos init` runtime state, not hand-written)
```

## Implemented in this bootstrap (2026-08-11)

| Component | SPEC | State |
|---|---|---|
| Core runtime, config, IDs, telemetry | SPEC-001 | `IMPLEMENTED` + `TESTED` |
| SQLite storage + migrations | SPEC-002 | `IMPLEMENTED` + `TESTED` |
| Repository layer | SPEC-003 | `IMPLEMENTED` + `TESTED` |
| Event bus (in-process + persisted) | SPEC-004 | `IMPLEMENTED` + `TESTED` |
| Job system (queue, worker, retry) | SPEC-005 | `IMPLEMENTED` + `TESTED` |
| Scheduler (cron/interval) | SPEC-006 | `IMPLEMENTED` + `TESTED` |
| Workflow engine (YAML DSL) | SPEC-007 | `IMPLEMENTED` + `TESTED` |
| Project discovery + mode detection | SPEC-008 | `IMPLEMENTED` + `TESTED` |
| Capability discovery + project manifest | SPEC-009 | `IMPLEMENTED` + `TESTED` |
| Knowledge: documents, chunking, FTS | SPEC-010 | `IMPLEMENTED` + `TESTED` |
| CLI (`init`, `doctor`, `db migrate`, `knowledge`, `workflows`, `runs`) | SPEC-001/007/010 | `IMPLEMENTED` + `TESTED` |

**Not yet implemented** (see `roadmaps/roadmap.md`): embeddings/vector retrieval, knowledge
graph, agent runtime beyond primitives, approvals UI, research engine, content engine, lead
intelligence, CRM, meetings, Academy, community, control center, external integrations.

## Development

From the repository root (`geos/`):

```bash
python -m unittest discover -s tests -t .    # 83 tests (stdlib, zero deps)
python -m geos.cli doctor                     # environment + config checks
```

See the repository `README.md` for the package layout.
