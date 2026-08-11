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
| A-007 | social-publish | Social | approval | draft → channel | SocialAgent | HUMAN_APPROVAL_REQUIRED | posts, reach | PLANNED |
| A-008 | meeting-invite | Meetings | qualification | lead → slots → calendar | MeetingAgent | HUMAN_APPROVAL_REQUIRED | meetings | PLANNED |
| A-009 | newsletter-send | Email | schedule | digest → ESP | NewsletterAgent | HUMAN_APPROVAL_REQUIRED | opens | PLANNED |

## Failure modes (all automations)

Every automation records: retryable/terminal errors, dead-letter, idempotency_key reuse,
approval waits, and a run trace (SPEC-001/005).

## Promotion rule

An automation moves from PLANNED → SPECIFIED → IMPLEMENTED → TESTED → VALIDATED → RELEASED only
via SDD; shadow mode first for anything touching external systems (ADR-0005).
