# GEOS Automation Catalog

> **State: CURRENT (bootstrap)** · Maturity: L0 MANUAL · L1 ASSISTED · L2 AUTOMATED DRAFT ·
> L3 AUTOMATED + APPROVAL · L4 AUTOMATED LOW-RISK · L5 AUTONOMOUS OPTIMIZATION
> Rule: never chase L5 indiscriminately; external actions require approval by default.

## Current (bootstrap)

| # | Name | Domain | Trigger | Input → Output | Agents/Tools | Approval | Metrics | Status |
|---|---|---|---|---|---|---|---|---|
| A-001 | daily-intelligence | Growth | scheduler (cron) | signals → daily brief | workflow (SPEC-007) | none (read-only) | runs, events | PLANNED |
| A-002 | knowledge-ingest | Knowledge | CLI `geos knowledge ingest` | docs → chunks → FTS | none (deterministic) | none | docs, chunks | ✅ IMPLEMENTED |
| A-003 | workflow-run | Core | CLI `geos workflows run` | yaml → run record | step agents (deterministic mocks) | configurable per step | duration, status | ✅ IMPLEMENTED |
| A-004 | lead-signal-capture | Leads | events | form/event → lead + signal | LeadIntelligenceAgent | none (internal) | leads, signals | PLANNED |
| A-005 | content-draft | Content | event/CLI | research → brief → draft | ResearchAgent, WriterAgent | CREATE_DRAFT = automatic | drafts | PLANNED |
| A-006 | blog-publish | Content | approval | draft → CMS | BlogAgent | HUMAN_APPROVAL_REQUIRED | published | PLANNED |
| A-007 | social-publish | Social | approval | draft → channel | SocialAgent | HUMAN_APPROVAL_REQUIRED | posts, reach | ✅ IMPLEMENTED (v0.8.0, SPEC-025: posts determinísticos por canal + agendamento; adapters reais de API em fases futuras) |
| A-008 | meeting-invite | Meetings | qualification | lead → slots → calendar | MeetingAgent | HUMAN_APPROVAL_REQUIRED | meetings | PLANNED |
| A-009 | newsletter-send | Email | schedule | digest → ESP | NewsletterAgent | HUMAN_APPROVAL_REQUIRED | opens | PLANNED |
| A-010 | research-run | Research | CLI/event | question → report+insights (mock) | ResearchAgent (determinístico) | none (read-only) | research rows, insights | ✅ IMPLEMENTED |
| A-011 | graph-extract | Knowledge | CLI `geos graph extract` | docs → nós/arestas | RuleBasedExtractor | none | nodes, edges | ✅ IMPLEMENTED |
| A-012 | hybrid-retrieval | Knowledge | CLI/workflow | query → hits+citações | HybridRetriever | none | hits, tokens | ✅ IMPLEMENTED |
| A-013 | content-factory (slice 1) | Content | cron/manual | research→brief→draft→social→approval→schedule | ResearchAgent, WriterAgent | HUMAN_APPROVAL_REQUIRED (publish) | runs, approvals | ✅ IMPLEMENTED (v0.2.0; draft persiste desde v0.3.0) |
| A-014 | content-engine | Content | CLI/workflow | topic → idea pontuada → brief → draft versionado | ContentEngine (determinístico) | none (internal) | content, versions, score | ✅ IMPLEMENTED (v0.3.0) |
| A-015 | content-repurpose | Content | CLI/workflow | draft → variantes por canal | ContentEngine.repurpose | none (internal, mock) | variants, sources | ✅ IMPLEMENTED (v0.3.0) |
| A-016 | research-synthesis | Research | CLI/workflow | question+fontes → síntese com citações [F#] | ResearchEngine + ModelProvider (SPEC-039) | none (read-only) | research, model, mock | ✅ IMPLEMENTED (v0.4.0; mock default, LLM se `models:` configurado) |
| A-017 | seo-audit | SEO | CLI `geos seo audit` | docs+content → issues persistidas | SeoEngine (determinístico, SPEC-023) | none (read-only) | audits, issues | ✅ IMPLEMENTED (v0.5.0) |
| A-018 | opportunity-collect | Growth | CLI `geos opportunities collect` | research insights + SEO gaps → opportunities (dedup por problema) | OpportunityEngine (SPEC-034) | none (read-only) | opportunities | ✅ IMPLEMENTED (v0.6.0) |
| A-019 | opportunity-score | Growth | CLI `geos opportunities score` | ICE/RICE explicável (breakdown + razões) | OpportunityEngine (SPEC-034) | none (read-only) | score, breakdown | ✅ IMPLEMENTED (v0.6.0) |
| A-020 | experiment-lifecycle | Growth | CLI `geos experiments` | oportunidade → hipótese → PROPOSED/RUNNING/COMPLETED + decisão/learning | ExperimentEngine (SPEC-034) | none (read-only; statuses internos) | experiments | ✅ IMPLEMENTED (v0.6.0) |
| A-021 | blog-prepare | Blog | CLI `geos blog prepare` | conteúdo APPROVED/SCHEDULED → post markdown + front matter | BlogEngine (SPEC-024) | none (read-only) | blog_posts | ✅ IMPLEMENTED (v0.7.0) |
| A-022 | blog-publish | Blog | CLI `geos blog publish [--approve]` | post → arquivo markdown (adapter) — **aprovação humana obrigatória** | BlogEngine + ApprovalEngine (SPEC-024, `blog.publish` = HUMAN_APPROVAL_REQUIRED) | write local (adapter), gated | path, url, approval | ✅ IMPLEMENTED (v0.7.0) |
| A-023 | social-prepare | Social | CLI `geos social prepare` | conteúdo APPROVED/SCHEDULED → post determinístico por canal (+ opcional `--at`) | SocialEngine (SPEC-025) | none (read-only) | social_posts | ✅ IMPLEMENTED (v0.8.0) |
| A-024 | social-schedule | Social | CLI `geos social due` / `schedule` | agendamento → fila SCHEDULED → vencidos listados | SocialEngine (SPEC-025 R4) | none (read-only; escrita exige publish aprovado) | scheduled_at, due | ✅ IMPLEMENTED (v0.8.0) |
| A-025 | social-publish | Social | CLI `geos social publish [--approve]` | post → arquivo por canal (adapter) — **aprovação humana obrigatória** | SocialEngine + ApprovalEngine (SPEC-025, `social.publish` = HUMAN_APPROVAL_REQUIRED) | write local (adapter), gated | path, approval | ✅ IMPLEMENTED (v0.8.0) |

## Failure modes (all automations)

Every automation records: retryable/terminal errors, dead-letter, idempotency_key reuse,
approval waits, and a run trace (SPEC-001/005).

## Promotion rule

An automation moves from PLANNED → SPECIFIED → IMPLEMENTED → TESTED → VALIDATED → RELEASED only
via SDD; shadow mode first for anything touching external systems (ADR-0005).
