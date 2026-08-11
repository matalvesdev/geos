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
├── specs/SPEC-001..025/034/035/038/039/103/106 ← specs implemented
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

| CLI (`init`, `doctor`, `db migrate`, `knowledge`, `workflows`, `runs`) | SPEC-001/007/010 | `IMPLEMENTED` + `TESTED` |
| Embeddings + vector store (hash provider, cache) | SPEC-011 | `IMPLEMENTED` + `TESTED` |
| Hybrid RAG (FTS+vector+graph, pesos configuráveis) | SPEC-012 | `IMPLEMENTED` + `TESTED` |
| Knowledge graph (extração determinística + CLI) | SPEC-013 | `IMPLEMENTED` + `TESTED` |
| Memory (TTL, sensibilidade) | SPEC-014 | `IMPLEMENTED` + `TESTED` |
| Research engine + vertical slice 1 (`content-factory`) | SPEC-021 | `IMPLEMENTED` + `TESTED` |
| Content engine (objetos, scoring, pipeline, versionamento) | SPEC-022 | `IMPLEMENTED` + `TESTED` |
| SEO engine (auditoria determinística) | SPEC-023 | `IMPLEMENTED` + `TESTED` |
| Blog publisher (markdown + front matter, approval-gated) | SPEC-024 | `IMPLEMENTED` + `TESTED` |
| Social scheduler (posts por canal, agendamento, worker L3, adapters reais) | SPEC-025 | `IMPLEMENTED` + `TESTED` |
| Opportunity + experiment engine (ICE/RICE explicável) | SPEC-034 | `IMPLEMENTED` + `TESTED` |
| Analytics (metric registry + insights por regra) | SPEC-035 | `IMPLEMENTED` + `TESTED` |
| Control Center (dashboard HTML estático) | SPEC-038 | `IMPLEMENTED` + `TESTED` (bootstrap) |
| Greenfield bootstrap (`geos bootstrap`) | SPEC-103 | `IMPLEMENTED` + `TESTED` |
| Integration planner (`geos plan`) | SPEC-106 | `IMPLEMENTED` + `TESTED` |
| Model providers (LLM OpenAI-compatible, síntese ancorada) | SPEC-039 | `IMPLEMENTED` + `TESTED` |

**Not yet implemented** (see `roadmaps/roadmap.md`): adapters reais de blog/social (CMS,
APIs), analytics, campaigns, lead intelligence, CRM, meetings, Academy, community,
control center, integrações externas.

## Development

From the repository root (`geos/`):

```bash
python -m unittest discover -s tests -t .    # 247 tests (stdlib, zero deps)
python -m geos.cli doctor                     # environment + config checks
```

See the repository `README.md` for the package layout.
