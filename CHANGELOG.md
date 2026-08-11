# Changelog

Todas as mudanças relevantes do GEOS são registradas aqui (spec §198). Formato
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e versionamento semântico.

## [0.1.0] — 2026-08-11 — Bootstrap

### Added

- **Core Runtime** (SPEC-001): configuração `geos.yaml` com validação determinística,
  IDs/traces, telemetria de runs (duração, modelo, tokens, custo, erros).
- **SQLite Storage + Migrations** (SPEC-002): banco local `.geos/geos.db` (WAL, FKs),
  sistema de migrações versionadas e idempotentes, FTS5.
- **Repository Layer** (SPEC-003): repositórios tipados (runs, events, jobs, approvals,
  documents/chunks, knowledge nodes/edges) — nenhum domínio depende de SQLite diretamente.
- **Event Bus** (SPEC-004): pub/sub em processo com log persistido e protocolo para
  adapters de brokers externos (Kafka/RabbitMQ/Redis…).
- **Job System** (SPEC-005): fila SQLite com status (PENDING→RUNNING→SUCCESS/FAILED/
  RETRYING/DEAD), idempotency_key, retry com backoff exponencial e dead-letter.
- **Scheduler** (SPEC-006): parser cron próprio (zero dependências) + schedules por
  intervalo, com enqueue idempotente.
- **Workflow Engine** (SPEC-007): DSL YAML declarativa (agentes/tasks/approvals,
  condições, retry, timeout), avaliador de condições restrito por AST (sem eval), runs
  persistidos.
- **Project Discovery & Mode Detection** (SPEC-008 / 101-102): detecção determinística
  GREENFIELD/BROWNFIELD/STANDALONE com evidências e confiança.
- **Capability Discovery & Manifest** (SPEC-009 / 104-107): detectores de stack
  (Spring Boot, React/Vite, Postgres, Flyway, CI, docs, ADRs, design system…), manifest
  `.geos/project-manifest.json` e Repository Registry.
- **Knowledge: Documents, Chunking, FTS** (SPEC-010): ingestão de Markdown com
  dedup por hash de conteúdo, chunking por headings/parágrafos e busca FTS5 com snippet.
- **CLI**: `geos init`, `doctor`, `db migrate`, `knowledge ingest/search`,
  `workflows list/run`, `runs list`, `approvals list`, `repo add/list`, `plan` (experimental).
- **Docs**: árvore `docs/geos/` (auditoria, contexto, visão, ADRs 0001-0006, roadmap,
  SPEC-001..010, catálogo de automações) e 83 testes (`unittest`, zero deps além de PyYAML).

### Security

- Condições de workflow avaliadas por AST whitelist — chamadas, imports e acesso a
  dunders são rejeitados (fail loud, nunca skip silencioso).
- Consultas SQL sempre parametrizadas; queries FTS sanitizadas.
