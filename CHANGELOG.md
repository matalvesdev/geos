# Changelog

Todas as mudanças relevantes do GEOS são registradas aqui (spec §198). Formato
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e versionamento semântico.

## [0.3.0] — 2026-08-11 — Content Engine + PyPI readiness + real embeddings

### Added

- **Content Engine** (SPEC-022): `ContentEngine` em `domains/content.py` com objeto
  tipado (18 tipos), scoring determinístico e explicável (9 componentes + breakdown +
  confiança 0.5 honesta), pipeline de status validado (`IDEA → BRIEFED → DRAFTED →
  REVIEWING → APPROVED → SCHEDULED → PUBLISHED → ARCHIVED`, transições ilegais falham
  com `ContentError`), repurposing determinístico (registra `repurposed-from:<id>`;
  nunca copia mecanicamente) e versionamento via `content_versions`.
- **Migration V3** (`content_phase2`): tabelas `content` + `content_versions` com
  índice único de slug.
- **CLI `geos content`**: `create`, `list`, `score`, `status`, `show`.
- **OpenAI-compatible embeddings** (SPEC-011): `OpenAIEmbeddingProvider` atrás do
  protocolo (stdlib `urllib`, zero deps; endpoint/modelo configuráveis — OpenAI,
  Azure, vLLM/Ollama locais; chave via env `GEOS_OPENAI_API_KEY`/`OPENAI_API_KEY`),
  factory `provider_from_config` lendo `knowledge.embeddings` do `geos.yaml`, flags
  `--provider hash|openai` em `geos knowledge ingest|reindex`.
- **Handlers**: `content.ideate`; `content.draft` agora persiste via ContentEngine
  (idempotente por tópico — runs agendados reusam o mesmo item).
- **PyPI readiness**: `pyproject.toml` corrigido (classifiers como lista PEP 621,
  license table, authors, keywords), sdist+wheel buildados e validados com
  `twine check` (bug latente de parse TOML descoberto e corrigido).

### Fixed

- `OpenAIEmbeddingProvider` agora converte timeout/disconnect (`TimeoutError`,
  `http.client.IncompleteRead`/`ConnectionResetError`, URLError) em `EmbeddingError`
  tipado — nenhuma exceção crua escapa do protocolo.
- `write_brief` valida status (`IDEA` apenas) — não rebobina mais itens PUBLISHED/ARCHIVED.
- Novelty counting via `COUNT(*)` SQL (era O(n) com cap de 1000 itens).
- Testes de regressão: idempotência do handler, guard do brief, contagem case-insensitive.

### Changed

- README: badges (CI, Python, licença, PyPI, testes), seção de features, contagens
  atualizadas (132 testes, SPEC-001..022). `geos.yaml` default documenta
  `knowledge.embeddings`.

## [0.2.0] — 2026-08-11 — Phase 1: Knowledge + Research

### Added

- **Embeddings & Vector Store** (SPEC-011): `HashEmbeddingProvider` determinístico (n-gram
  hashing, L2-normalizado, zero deps) + `SqliteVectorStore` (upsert/delete/search/hybrid),
  cache por `content_hash` (spec §17), tabela `embeddings` (migration V2).
- **Hybrid RAG** (SPEC-012): `HybridRetriever` combinando FTS5 + vetores + graph boost com
  pesos configuráveis, rerank heurístico, proveniência por hit e contexto com citações.
- **Knowledge Graph** (SPEC-013): `RuleBasedExtractor` determinístico (dicionário + keywords +
  frases-problema, sem palpite de frases capitalizadas) + `GraphService` (neighbors,
  related_documents, stats); CLI `geos graph extract` / `geos graph inspect`.
- **Memory** (SPEC-014): `MemoryStore` com TTL, sensibilidade e scopes + `WorkingMemory`;
  tabela `memories` (migration V2).
- **Research Engine** (SPEC-021): pipeline QUESTION → PLAN → SOURCES → EXTRACTION → SYNTHESIS
  → INSIGHT → KNOWLEDGE, determinístico sobre o índice local (synthesis `mock: True`),
  persistido em `research`/`insights` + nós INSIGHT + evento `research.completed`;
  CLI `geos research run`. Nunca inventa fontes.
- **Vertical slice 1**: workflow `content-factory` (research → knowledge → brief → draft →
  social → aprovação obrigatória → schedule) + handlers `research.run`/`content.brief`/
  `schedule.record` + CLI `geos workflows schedule` / `geos workflows worker` (job
  `workflow.run`) — SPEC-006 wiring de triggers cron.
- **Migration V2** (`knowledge_phase1`): tabelas `embeddings`, `memories`, `research`,
  `insights`. **CLI**: `knowledge reindex`, `graph extract/inspect`, `research run`,
  `workflows schedule/worker`.
- 30 novos testes (113 no total, `unittest`).

### Fixed

- **Ranking híbrido FTS (bug silencioso)**: `bm25()` do FTS5 retorna scores negativos
  (mais negativo = melhor match); a normalização usava `abs(rank)`, invertendo a ordem
  dos resultados. Corrigido para normalizar em `-rank` (mais forte = maior score) com
  teste de regressão isolado (SPEC-012).
- **`graph related_documents`**: removido N+1 (era `list_edges(2000)` dentro do loop de
  topics + lookup por nó); agora é um único JOIN SQL parametrizado (SPEC-013).
- `HybridRetriever` não acessa mais atributo privado `vector_store._provider` (nova
  property pública `SqliteVectorStore.provider`); cache de embeddings limitado a 10k
  entradas por processo.

### Changed

- Ingestão agora calcula embeddings por chunk (cache por hash; `--no-embed`/reindex
  disponíveis). `workflows_dir` default `workflows` com fallback ao diretório do pacote.

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
