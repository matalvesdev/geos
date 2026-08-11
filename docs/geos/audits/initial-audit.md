# Initial Audit — Rule Zero

> **State: CURRENT** · Date: 2026-08-11 · Auditor: GEOS bootstrap (Buffy)
> Method: full tree inspection, file-picker/code-searcher survey, key-file reads.
> Classification: KEEP · IMPROVE · REFACTOR · MERGE · REPLACE · DEPRECATE · ARCHIVE · CREATE

## 1. What this workspace is

A company workspace for **Zetra / Azeetra** containing:

1. **`zetra-one/`** — the canonical product repository: Spring Boot API, React/Vite web,
   PostgreSQL, Flyway, GitHub Actions CI, and an extensive `docs/` tree (ADRs, domain,
   ingestion, marketing, validation, operations, QA, runbooks).
2. **Zetra Company Library** (`dist/`, `Zetra-Company-Library-v1.0/`) — versioned company
   documentation releases with Excel backlogs (marketing, academy, product, knowledge).
3. **Doc-build Python tooling** at the root (`build_*.py`, `approve_*.py`, `normalize_*`,
   `polish_*`) — scripts that assembled the Company Library releases.
4. **`OPENCODE_EXECUTION_INSTRUCTION.md`** — instruction for a previous doc-engineering pass.
5. **`.playwright-cli/`** — transient browser-capture artifacts.

## 2. Technology inventory

| Area | Finding | Source |
|---|---|---|
| Backend | Java 21, Spring Boot 3.5.16, Maven, Flyway, JDBC | `zetra-one/services/api/pom.xml` |
| Frontend | React 19, Vite 7, Tailwind 4, TanStack Query, Zod, Vitest | `zetra-one/services/web/package.json` |
| Database | PostgreSQL 17 (compose), Flyway migrations | `zetra-one/compose.yaml`, ADR-0001 |
| CI/CD | GitHub Actions (`ci.yml`) | `zetra-one/.github/workflows/ci.yml` |
| Containers | Docker Compose (postgres/api/web) | `zetra-one/compose.yaml` |
| Data | Public CGU datasets with manifests + validation JSONs | `zetra-one/datasets/` |
| Tooling | TypeScript analysis scripts, Google Apps Scripts | `zetra-one/tools/` |
| Docs | ADRs 0001–0009, domain model, ingestion policies, marketing, validation protocol | `zetra-one/docs/` |

## 3. Company/strategy inventory

| Asset | Finding |
|---|---|
| Brand | **Azeetra** adopted (BRAND-NAMING-DECISION-001); code still `zetra`; legal clearance pending |
| Product | Zetra One — "Trusted Origin"; domain: Cash Application; question: "De onde veio esse dinheiro?" |
| Phase | VALIDATION / PILOT PREPARATION (PROGRAM-STATUS.md, 2026-08-10) |
| Marketing | MKT-009 Marketing Operating System (manual); MKT-EXP-001 active; MKT-GATE-001 released (2026-08-11) |
| SEO | MKT-005 initial PT-BR foundation; measurement not yet live |
| Academy | Separate learning program; content backlog (ACAD-008) exists |
| Community | Not launched; planned |
| CRM/Leads | None automated; lead acquisition = Google Forms (DOMAIN-004) + manual trackers |
| Sales/Meetings | None automated |
| Analytics | None wired to product (Search Console/GA planned, privacy-compatible) |
| Knowledge | Company Library v1.0 + extensive docs; no RAG/graph/agent layer |

## 4. Classification

### KEEP (valid work, do not recreate)
- `zetra-one/services/api` + `services/web` — canonical product implementation (BUILD-001+). **Do not modify.**
- `zetra-one/docs/adr/ADR-0001..0009` — disciplined ADR practice; GEOS will mirror it.
- `zetra-one/docs/marketing/MKT-009-Marketing-Operating-System.md` — the de-facto marketing OS; GEOS operationalizes, never replaces.
- `zetra-one/docs/marketing/CLAIMS-REGISTRY.md` — claims/evidence governance (GEOS reuses the pattern).
- `zetra-one/docs/validation/*` — evidence discipline; GEOS inherits "no evidence → no claim".
- `zetra-one/datasets/` — official CGU datasets + validation manifests.
- `zetra-one/.github/workflows/ci.yml`, `compose.yaml` — CI/CD + local infra.

### IMPROVE (keep, evolve)
- MKT-009 → will gain machine-executable artifacts (editorial calendar, content pipeline) via GEOS domains.
- Marketing measurement → wire Search Console/GA through an `AnalyticsProvider` (roadmap).
- `zetra-one/docs/marketing-reconciliation/*` → can be automated (doc diff → changelog) by GEOS.

### REFACTOR / MERGE
- Root doc-build Python scripts (`build_*`, `approve_*`, `normalize_*`, `polish_*`) → group into a
  single `scripts/` area or adopt GEOS workflows; they are Company Library tooling, not GEOS. **MERGE**
  into a documented location during a later cleanup; nothing deleted without decision.

### ARCHIVE (transient/historical)
- `.playwright-cli/` — transient browser captures; candidate for `.gitignore`/cleanup (decision required).
- Historical pilot artifacts already declared non-evidence in `PROGRAM-STATUS.md` — keep as history, never cite as evidence.

### CREATE (this bootstrap)
- `geos/` — Python package (Core, storage, intelligence, CLI).
- `.geos/` — runtime state: `geos.yaml`, `geos.db`, cache, `project-manifest.json`.
- `docs/geos/` — this documentation tree (audit, context, vision, ADRs, roadmap, specs, catalog).
- Repository Registry (first entry: `zetra-one`), capability map, adoption plan (SPEC-008/009).

## 5. Gaps identified (GEOS-relevant)

| Capability | Current state | GEOS action |
|---|---|---|
| Knowledge retrieval | None (docs are static files) | CREATE: ingestion + FTS + hybrid RAG (SPEC-010+) |
| Knowledge graph | None | CREATE (planned) |
| Agent runtime | None | CREATE: primitives first (SPEC-001/007) |
| Scheduling | None for marketing ops | CREATE: scheduler (SPEC-006) |
| CRM | None | CREATE internal fallback (planned); adapters later |
| Social scheduling | Manual | CREATE (planned; human-approval gated) |
| Analytics | Not wired | INTEGRATE (planned) |
| Blog/CMS | None (website surface local `/estudos`) | INTEGRATE/CREATE (planned) |
| Approvals | Manual (MKT-GATE-001) | CREATE: approval engine (planned) |

## 6. Risks & notes
- Brand: Azeetra clearance pending — GEOS must not produce external assets that hard-code the
  brand beyond what the founder approved.
- No customer evidence exists; GEOS must never fabricate it (inherits Zetra's rule).
- Zero-dependency principle: GEOS bootstrap avoids external services (SQLite, in-process bus).
