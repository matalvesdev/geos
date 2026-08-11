# GEOS Roadmap

> **State: CURRENT** · Date: 2026-08-11 · Status: foundation in flight
> Every phase ends with: tests green, docs updated, CHANGELOG entry, self-audit note.

## Phase 0 — Foundation (bootstrap, in progress)

| Item | SPEC | Status |
|---|---|---|
| Core runtime, config, IDs, telemetry | SPEC-001 | ✅ IMPLEMENTED + TESTED |
| SQLite storage + migrations | SPEC-002 | ✅ IMPLEMENTED + TESTED |
| Repository layer | SPEC-003 | ✅ IMPLEMENTED + TESTED |
| Event bus | SPEC-004 | ✅ IMPLEMENTED + TESTED |
| Job system | SPEC-005 | ✅ IMPLEMENTED + TESTED |
| Scheduler (cron/interval) | SPEC-006 | ✅ IMPLEMENTED + TESTED |
| Workflow engine (YAML DSL) | SPEC-007 | ✅ IMPLEMENTED + TESTED |
| Project discovery + mode detection | SPEC-008 | ✅ IMPLEMENTED + TESTED |
| Capability discovery + project manifest | SPEC-009 | ✅ IMPLEMENTED + TESTED |
| Knowledge: documents, chunking, FTS | SPEC-010 | ✅ IMPLEMENTED + TESTED |
| Open-source readiness (LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, examples/) | — | PLANNED |

## Mandated adoption specs (foundational; before advanced external automations)

Required by the Installation, Bootstrap & Adoption Model (spec §73). Statuses:

| SPEC | Title | Status |
|---|---|---|
| SPEC-101 | Project Discovery | ✅ IMPLEMENTED (core of SPEC-008) |
| SPEC-102 | Mode Detection (greenfield/brownfield/standalone) | ✅ IMPLEMENTED (SPEC-008) |
| SPEC-103 | Greenfield Bootstrap (`geos init --mode greenfield`, `geos bootstrap`) | ✅ IMPLEMENTED + TESTED (bootstrap idempotente, seed, automações) |
| SPEC-104 | Brownfield Audit (`geos audit`, capability map) | ✅ PARTIAL (SPEC-009; full `geos audit` output planned) |
| SPEC-105 | Capability Discovery (detector plugins) | ✅ PARTIAL (SPEC-009 core detectors; plugin API PLANNED) |
| SPEC-038 | Control Center (dashboard estático autocontido) | ✅ IMPLEMENTED + TESTED (bootstrap: `control-center build`) |
| SPEC-106 | Integration Planner (`geos plan`) | ✅ IMPLEMENTED + TESTED (plano em 5 fases, read-only) |
| SPEC-107 | Repository Registry (`geos repo add/list/scan`) | PARTIAL (registry + zetra-one seed; CLI planned) |
| SPEC-108 | Multi-Repo / Standalone Control Plane | PLANNED |
| SPEC-109 | Shadow Mode | PLANNED (pattern specified in ADR-0005) |
| SPEC-110 | Feature Flags | ✅ PARTIAL (config `features.*` honored by CLI; runtime gating PLANNED) |
| SPEC-111 | Migration Safety (dual-run, cutover, rollback) | PLANNED |
| SPEC-112 | Uninstall & Reversibility (`geos uninstall --keep-data`) | PLANNED |

## Phase 1 — Knowledge + Research (first vertical slice)

| Item | SPEC | Status |
|---|---|---|
| Embeddings (provider + vector store SQLite, cache por content_hash) | SPEC-011 | ✅ IMPLEMENTED + TESTED |
| Hybrid RAG (FTS + vector + graph boost, pesos configuráveis, rerank, citações) | SPEC-012 | ✅ IMPLEMENTED + TESTED |
| Knowledge Graph (extração determinística + nós/arestas + graph extract/inspect) | SPEC-013 | ✅ IMPLEMENTED + TESTED |
| Memory (MemoryStore com TTL/sensibilidade + WorkingMemory) | SPEC-014 | ✅ IMPLEMENTED + TESTED |
| Research Engine (pipeline determinístico sobre a base local) | SPEC-021 | ✅ IMPLEMENTED + TESTED |
| Vertical slice 1 (research → brief → draft → social → approval → schedule) | SPEC-007/021 | ✅ workflow `content-factory` + `workflows schedule/worker` |
| Embeddings treinados/LLM (providers reais atrás dos protocolos) | SPEC-011 | ✅ OpenAI-compatible provider + factory (`knowledge.embeddings`) |
| ModelProvider (protocolo + OpenAI-compatible + síntese ancorada com citações) | SPEC-039 | ✅ IMPLEMENTED + TESTED (`models info/test`, fallback mock honesto) |

O research engine é determinístico sobre o índice local por default (synthesis `mock: True`);
com `models:` configurado, a síntese é gerada por modelo **estritamente ancorada nas fontes**
recuperadas (citações [F#], `mock: False`, modelo/provedor persistidos — SPEC-039). Se o
provider falhar, cai para o mock (nunca fabrica conteúdo).

## Phase 2 — Content + Growth engines

| Item | SPEC | Status |
|---|---|---|
| Content Engine (content object, scoring determinístico, pipeline validado, repurposing) | SPEC-022 | ✅ IMPLEMENTED + TESTED (CLI `geos content`, handlers idempotentes) |
| SEO Engine (auditoria determinística: broken links, órfãos, thin, gaps, cannibalização, decay) | SPEC-023 | ✅ IMPLEMENTED + TESTED (CLI `seo audit/issues`) |
| Opportunity + Experiment Engine (collect research+SEO, ICE/RICE explicável, lifecycle validado) | SPEC-034 | ✅ IMPLEMENTED + TESTED (CLI `opportunities`/`experiments`) |
| Blog Publisher (markdown + front matter, adapters local/CMS, aprovação humana obrigatória) | SPEC-024 | ✅ IMPLEMENTED + TESTED (CLI `blog prepare/publish`, `content draft`) |
| Social Scheduler (human-approval gated, posts determinísticos por canal, agendamento) | SPEC-025 | ✅ IMPLEMENTED + TESTED (CLI `social prepare/list/due/publish`, migration V8) |
| Analytics (AnalyticsProvider + metric registry + insights OBSERVATION/HYPOTHESIS/INVESTIGATION) | SPEC-035 | ✅ IMPLEMENTED + TESTED (CLI `analytics collect/metrics/insights`, migration V9) |
| Campaign Orchestration (lifecycle, content/social/experiment linking, metrics, budget) | SPEC-040 | ✅ IMPLEMENTED + TESTED (CLI `geos campaigns`, migration V10) |

Automations: `daily-growth-intelligence` (SPEC-143), `weekly-content`, `weekly-growth-review`,
changelog/release automation (SPEC-148) — all behind approvals and feature flags.

## Phase 3 — Leads, CRM, Meetings

| Item | SPEC | Status |
|---|---|---|
| Lead Intelligence (lifecycle, scoring, qualification, interactions) | SPEC-026/027/028 | ✅ IMPLEMENTED + TESTED (CLI ) |
| CRM (deal pipeline, stages, activities, pipeline summary) | SPEC-029 | ✅ IMPLEMENTED + TESTED (CLI ) |
| Meeting Scheduling (lifecycle, types, analytics) | SPEC-031/032 | ✅ IMPLEMENTED + TESTED (CLI ) |
| Email Nurture (sequences, enrollments, suppression) | SPEC-033 | ✅ IMPLEMENTED + TESTED (CLI ) |

Remaining: SPEC-030 Next Best Action, SPEC-032 Google Calendar/Meet adapter (external API integration).

## Phase 4 — Education, Community, DevRel

- SPEC-036 Academy (tracks/courses/modules/lessons/labs/challenges/assessments/certifications),
  SPEC-037 Community (Discord blueprint, question→education loop), DevRel, advanced social
  (Instagram planner/writer/creative/analyst), campaign orchestration.

## Phase 5 — Control Center + Intelligence

- SPEC-038 Control Center (overview, signals, research, agents, runs, content, calendar, SEO,
  growth, experiments, leads, pipeline, meetings, academy, community, assets, approvals,
  knowledge, costs, health, settings), RAG debugger, agent-run debugger, backups, self-audit,
  self-improvement loop (observation → proposal → SPEC → review → implementation).

## Non-goals (this roadmap)

- No cold-outreach/spam machinery ever (spec §139, §220).
- No uncontrolled agent swarms; every collaboration has goal/budget/exit conditions.
- No replacement of existing Zetra One systems without a SPEC and dual-run validation.
