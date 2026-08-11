# Roadmap

Documento completo e vivo: [`docs/geos/roadmaps/roadmap.md`](docs/geos/roadmaps/roadmap.md).
Resumo das fases:

| Fase | Conteúdo | Status |
|---|---|---|
| **0 — Foundation** | Core runtime, SQLite, repositórios, event bus, jobs, scheduler, workflow engine, discovery (mode/capabilities), knowledge + FTS, CLI, docs | ✅ v0.1.0 (bootstrap) |
| 0.5 — OSS readiness | LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, examples, CI | ✅ 2026-08-11 |
| 1 — Knowledge + Research | Embeddings/VectorStore, Hybrid RAG, Knowledge Graph, Memory, Research Engine, vertical slice 1 (research→content→approval) | PLANNED |
| 2 — Content + Growth | Content engine, SEO, blog publisher, social scheduler (approval-gated), campaigns, analytics | ✅ parcial (SPEC-022/023/024/025/034/035) — campaigns PLANNED |
| 3 — Leads, CRM, Meetings | Lead intelligence, scoring (explicável), qualification, CRM (SQLite fallback), next best action, meeting scheduling (Google Calendar/Meet adapter) | PLANNED |
| 4 — Education, Community, DevRel | Academy (tracks/courses/labs/certifications), community (Discord blueprint), DevRel, social avançado | PLANNED |
| 5 — Control Center | Dashboard, RAG debugger, run debugger, backups, self-audit, self-improvement | PLANNED |

Specs de adoção obrigatórias (SPEC-101..112) estão mapeadas no roadmap completo; o
padrão Shadow Mode + feature flags precede qualquer automação externa (ADR-0005).

Princípio: **nunca busque L5 (autonomia total) indiscriminadamente** — automações
externas exigem SPEC, shadow mode, aprovação e validação.
