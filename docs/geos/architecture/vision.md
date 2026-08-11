# GEOS Architecture Vision

> **State: CURRENT** · Date: 2026-08-11 · Status: approved direction for bootstrap; refined via ADRs.

## 1. Thesis

GEOS is not a chatbot, a prompt collection, or a content farm. It is an **agentic organizational
growth platform** — a framework that converts the continuous loop:

```
MARKET → SIGNALS → RESEARCH → KNOWLEDGE → STRATEGY → CONTENT → DISTRIBUTION → AUDIENCE →
LEADS → QUALIFICATION → MEETINGS → OPPORTUNITIES → CUSTOMERS → EDUCATION → COMMUNITY →
ANALYTICS → LEARNING → (better knowledge, strategy, product, distribution) → …
```

into executable, observable, measurable machinery — while keeping **human approval at every
meaningful external-risk boundary** and **organizational knowledge as the durable asset** (models,
providers and channels are replaceable; knowledge is not).

## 2. Principles (operative subset)

1. Teach before selling; education is distribution; documentation is product.
2. Every campaign has a hypothesis; every experiment produces knowledge.
3. Deterministic logic preferred over LLMs when traditional code solves it better.
4. Agents are specialized; no god agent; no uncontrolled swarms (goal, budget, exit conditions).
5. Human approval required for meaningful external risk; policies are declarative.
6. Data provenance preserved; conflicts recorded, never silently resolved.
7. Local-first: SQLite + in-process infrastructure; external systems arrive via adapters.
8. Minimum invasion in brownfield: reuse → adapter → wrap → create, in that order.
9. Automate repetitive work, never accountability.

## 3. System architecture

```
                    GEOS CONTROL PLANE (CLI / API / future dashboard)
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        │                          │                           │
    WORKFLOW ENGINE          AGENT RUNTIME               POLICY/APPROVAL
        │                          │                           │
        └──────────────────────────┼───────────────────────────┘
                                   ↓
                        EVENT BUS / JOB QUEUE / SCHEDULER
                                   ↓
                        INTELLIGENCE LAYER (Knowledge)
        ┌──────────────────────────┼───────────────────────────┐
        │                          │                           │
      SQLite (SQL+FTS)        Retrieval (RAG)              Graph (planned)
        │                          │                           │
        └──────────────────────────┼───────────────────────────┘
                                   ↓
                            DOMAIN LAYERS
   research · content · seo · social · leads · crm · meetings · academy · community · analytics
                                   ↓
                           ACTION GATEWAY (approvals)
                                   ↓
            integrations (search · calendar · email · social · cms · crm · analytics · creative)
```

## 4. Core primitives

`Agent` · `Task` · `Workflow` · `Tool` · `Trigger` · `Event` · `Artifact` · `Memory` ·
`Knowledge` · `Approval` · `Policy` · `Schedule` · `Run` · `Job` · `Metric` · `Experiment` ·
`Lead` · `Meeting` · `Connector` · `Provider`.

## 5. Storage & data

- **SQLite is the default** (local-first, zero infra). A repository/interface layer means no domain
  depends on SQLite directly (SPEC-002/003); PostgreSQL/object/vector/graph adapters are future
  provider implementations.
- Tables cover: runs, events, jobs, workflow runs, documents, document_chunks, knowledge_nodes,
  knowledge_edges, memories, approvals, audit_logs, analytics_snapshots (SPEC-002).

## 6. Intelligence

- Ingestion pipeline: SOURCE → FETCH → PARSE → NORMALIZE → CLEAN → DEDUPLICATE → CHUNK →
  METADATA → EMBED → INDEX → GRAPH → KNOWLEDGE.
- FTS via SQLite FTS5 (implemented, SPEC-010). Embeddings/vector retrieval behind provider
  interfaces (`EmbeddingProvider`, `VectorStore` — interfaces now, implementations later).
- Retrieval scoring is configurable (semantic/keyword/graph/recency/authority), never hard-fixed.

## 7. Security & operations

- Prompts are data when untrusted; system policy is never redefinable by external content.
- Secrets never in repo (`.env.example`); least privilege; PII classification
  (PUBLIC/INTERNAL/CONFIDENTIAL/PII/SECRET); deletion propagation planned.
- Telemetry: every run records trace_id/span_id, duration, model, tokens, cost, tools, errors,
  retries, approvals (SPEC-001). Run budgets and circuit breakers planned.

## 8. Installation model (this workspace)

- **BROWNFIELD / SIDECAR**: GEOS lives at `geos/`, connects to `zetra-one/` via Repository
  Registry, isolated SQLite, shadow mode first, feature-flagged adoption (ADR-0005, SPEC-008/009).

## 9. Open-source readiness (planned)

README, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, ROADMAP, ARCHITECTURE,
examples/, docs/ — under `geos/` (roadmap phase 0.5).

## 10. Ultimate property

**MARKET SIGNALS → ORGANIZATIONAL INTELLIGENCE → COORDINATED ACTION → MEASURABLE LEARNING.**
GEOS is the Organizational Learning Machine.
