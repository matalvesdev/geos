# Company Context — Zetra / Azeetra

> **State: CURRENT** · Date: 2026-08-11 · Evidence status: `VERIFIED` (from repo) · `ASSUMPTION` ·
> `UNKNOWN` · `NEEDS_VALIDATION`. **No facts are invented.**

## Identity

| Field | Value | Status |
|---|---|---|
| Company brand | **Azeetra** (pronounced êi-zi-tra) | VERIFIED (BRAND-NAMING-DECISION-001 v2.0, founder decision) |
| Code/package brand | `zetra` (unchanged until separate migration) | VERIFIED |
| Category | Decision Intelligence for Financial Operations | VERIFIED (PROGRAM-STATUS.md) |
| Product | **Zetra One**; wedge: **Trusted Origin** | VERIFIED |
| Core question | "De onde veio esse dinheiro?" (Where did this money come from?) | VERIFIED |
| Initial domain | Cash Application (Statement as root aggregate) | VERIFIED (ADR-0002, domain model) |
| Phase | MVP técnico implementado; VALIDATION / PILOT PREPARATION | VERIFIED (2026-08-10) |

## Vision / mission / problem

- **Problem**: finance/ops practitioners face credits without a trusted origin; reconciliation and
  decision take too long and rely on fragile evidence chains. *(ASSUMPTION — problem framing from
  product docs; user validation pending)*
- **Experience**: Guided Work + Decision Card; origin intelligence is internal capability, not the
  headline. *(VERIFIED)*
- **Target decision latency**: < 30 seconds — explicitly **a hypothesis to measure, not a proven
  result**. *(VERIFIED as hypothesis)*

## Market / ICP / personas

- Practitioners in financial operations (cash application, receivables, reconciliation). ICP detail
  pending: DOMAIN-004 research operations are built but **contacts/sessions remain at zero**.
  *(NEEDS_VALIDATION)*
- Learner personas for Academy: finance ops learners, accounting students, practitioners.
  *(ASSUMPTION — Academy backlog exists, no learner data)*
- Competitors: benchmark references named in the GEOS spec (Stripe, Nubank, iFood, AbacatePay…)
  are conceptual references, not a validated competitive analysis. *(ASSUMPTION)*

## Business model / pricing / revenue

- **UNKNOWN** — no revenue model, pricing, or commercial evidence in the repository. GEOS must not
  fabricate these.

## Marketing / growth state

| Asset | Status |
|---|---|
| MKT-009 Marketing Operating System | VERIFIED — comprehensive manual OS (principles, audience, messaging, distribution) |
| MKT-EXP-001 experiment | VERIFIED — active |
| MKT-GATE-001 | VERIFIED — released 2026-08-11: 4 founder-led problem-first copies, LinkedIn, ≤2/week, no deep link |
| Publications | VERIFIED — **zero published**; impression ≠ demand |
| SEO (MKT-005) | VERIFIED — PT-BR foundation by problem intent; measurement pending |
| Website/education surface | VERIFIED — local `/estudos` surface; public permalinks pending |
| Paid acquisition / result claims / customer evidence | VERIFIED — **blocked** at this phase |

## Education / Academy

- Academy is a **separate learning program**, not an MVP feature; may educate the market and recruit
  research/design partners. *(VERIFIED)*
- Content backlog exists (`ACAD-008`), no runtime. *(VERIFIED)*
- Commercial content, certifications and result claims must not precede product evidence. *(VERIFIED)*

## Community / DevRel

- **UNKNOWN** — community and DevRel are planned (MKT-009 mentions) but not launched.

## Technology

- Canonical: Java 21 + Spring Boot 3.5 + React 19/Vite 7 + PostgreSQL 17 + Flyway + GitHub Actions.
  *(VERIFIED)*
- Product events: transactional outbox exists (ADR-0004). *(VERIFIED)*
- No analytics wiring, no CMS automation, no CRM, no scheduling infra for marketing. *(VERIFIED)*

## Data / privacy posture

- LGPD-aware; research consent notices exist (RESEARCH-CONSENT-AND-DATA-NOTICE). *(VERIFIED)*
- No customer data in repo; official public datasets only. *(VERIFIED)*

## GEOS implications
1. GEOS operates on Zetra in **BROWNFIELD/SIDECAR** mode: read, index, propose — never modify
   product code (ADR-0005).
2. GEOS inherits the evidence bar: no fabricated claims, no synthetic metrics promoted.
3. Brand usage of "Azeetra" in GEOS-generated assets follows MKT-GATE-001 boundaries.
4. First GEOS value: **operationalize MKT-009** (knowledge, research, content drafts, approvals)
   and **structure the DOMAIN-004 lead pipeline** — both planned, not yet implemented.
