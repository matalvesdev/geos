# Changelog

Todas as mudanças relevantes do GEOS são registradas aqui (spec §198). Formato
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e versionamento semântico.

## [0.8.0] — 2026-08-11 — Social Scheduler (SPEC-025)

### Added

- **Social Scheduler** (SPEC-025, spec master §78–79): transforma conteúdo aprovado em
  posts determinísticos por canal — hook (1ª linha do body) + excerto + CTA + hashtags
  (keywords slugificadas com acentos normalizados, dedup, máx. 5).
- **Limites honestos por canal** (SPEC-025 R2): `x`=280, `linkedin`=3000,
  `bluesky`=300, `instagram`=2200 — o builder nunca excede; truncamento marca
  `truncated` (evento `social.prepared`), nunca corta em silêncio.
- **Aprovação humana obrigatória** (spec §47): `social.publish` é
  HUMAN_APPROVAL_REQUIRED; sem decisão, nada externo acontece — post fica
  `APPROVAL_PENDING` com approval reusado em republishes gated (sem spam na fila).
- **Agendamento** (SPEC-025 R4): `--at` no prepare registra `scheduled_at`; publish
  aprovado com data futura → `SCHEDULED` (nada externo até o horário); `due` lista os
  vencidos para o scheduler/worker futuro.
- **Adapters**: protocolo `SocialAdapter` + registro por nome; `LocalSocialAdapter`
  (escreve `<channel>-<slug>.txt` em dir configurado, default `social/`). APIs reais
  (X/LinkedIn/Bluesky/Instagram) ficam para fases futuras atrás do mesmo protocolo.
- **Migration V8** (`social_scheduler`): tabela `social_posts` (status DRAFT →
  APPROVAL_PENDING → SCHEDULED/PUBLISHED/FAILED, índice único (content_id, channel),
  scheduled_at, approval_id).
- **CLI**: `geos social prepare/list/due/publish [--approve] [--by] [--channel]
  [--at]`.
- 25 novos testes (208 no total).

### Fixed

- **Hashtags com acentos** (revisão durante o SPEC-025): slugify puro gerava
  `finan-as` para `finanças`; agora NFKD-normaliza antes (ASCII determinístico).
- **Limite de canal estourado** (revisão): o antigo piso de 20 chars por parte podia
  somar além do limite; agora o orçamento reserva as hashtags e há safety net final
  (`chars` nunca excede o limite, SPEC-025 R2).
- **Re-prepare de post FAILED quebrava** (revisão): o índice único (content_id,
  channel) estourava IntegrityError cru; agora a linha FAILED é reusada em place.
- **Hashtags duplicadas no arquivo** (smoke test): renderer agora monta as hashtags
  do campo `hashtags` exatamente uma vez (texto nunca embute hashtags).

### Changed

- README (208 testes, features de social), roadmap SPEC-025 ✅, catálogo de automações
  (A-007/A-023..A-025).

## [0.7.0] — 2026-08-11 — Blog Publisher (SPEC-024)

### Added

- **Blog Publisher** (SPEC-024, spec master §75–77): transforma conteúdo aprovado em
  posts markdown publicáveis — deterministic markdown + **front matter YAML** (title,
  slug, date, type, status, keywords, summary, sources, mock, content_id, version).
- **Aprovação humana obrigatória** (spec §47): `blog.publish` é
  `HUMAN_APPROVAL_REQUIRED`; sem decisão, nada externo acontece — o post fica
  `APPROVAL_PENDING` com approval registrado e o publish reexecutado **reusa o mesmo
  approval pendente** (sem spam na fila de aprovações).
- **Adapters**: protocolo `BlogAdapter` + registro por nome; `LocalMarkdownAdapter`
  (escreve `<slug>.md` no diretório configurado, default `blog/`). WordPress/Ghost
  ficam para fases futuras atrás do mesmo protocolo.
- **Migration V7** (`blog_publisher`): tabela `blog_posts` (status DRAFT →
  APPROVAL_PENDING → PUBLISHED/FAILED, slug único, publish_path/url/at, approval_id).
- **CLI**: `geos blog prepare/list/publish [--approve] [--by]` + novo `geos content
  draft` (produz o rascunho/body pelo CLI — antes só pelo workflow).
- 15 novos testes (183 no total).

### Fixed

- **Markdown quebrado (SPEC-022, bug antigo exposto pelo publisher)**: `_build_brief`/
  `_build_draft`/`_repurpose_body` emitiam o texto literal `\n` (backslash+n) em vez
  de quebras de linha reais — posts publicados não renderizavam. Corrigido (19
  sequências) com regressão que garante markdown renderizável.
- **Decisão de aprovação só após o publish ter sucesso** (review): adapter que falha →
  post `FAILED` + approval permanece `PENDING` (a trilha reflete o desfecho real).
- **Trilha de aprovação preservada em falha**: post `FAILED` mantém `approval_id`.
- Contrato de adapters: `get_adapter` tolera adapters sem arg `publish_dir`.

### Changed

- README (183 testes, features de blog), roadmap SPEC-024 ✅, catálogo de automações.

## [0.6.0] — 2026-08-11 — Opportunity + Experiment Engine (SPEC-034)

### Added

- **Opportunity Engine** (SPEC-034, spec §102): coleta oportunidades de **research
  insights** (CONTENT_OPPORTUNITY/KNOWLEDGE_GAP) + **SEO content gaps** com dedup
  idempotente **por problema** (ref `research:{id}:{slug}` — múltiplas oportunidades
  do mesmo relatório são todas criadas, não só a primeira).
- **Scoring explicável ICE/RICE**: `impact × confidence × ease / 100` (ICE) e
  `reach × impact × confidence / effort` (RICE), componentes com defaults neutros
  honestos, breakdown persistido com fórmula + razões por componente — score nunca
  é só um número (spec §114). Priorização por score desc, top-N, filtro por status.
- **Experiment Engine** (spec §101): de oportunidade OPEN → experimento PROPOSED
  (hipótese de template ancorada nas evidências, métrica primária, change, audience),
  transições validadas (PROPOSED → RUNNING → COMPLETED, CANCELLED), complete exige
  `result` + `learning`, decisão ADOPT/REJECT/ITERATE, eventos `experiment.proposed`/
  `experiment.completed`; oportunidade marcada EXPERIMENTING.
- **Migration V6** (`growth`): tabelas `opportunities` (status OPEN/EXPERIMENTING,
  componentes, score/score_method/breakdown JSON) + `experiments`.
- **CLI**: `geos opportunities collect/list/create/score` e `geos experiments
  create/status/complete/list`.
- 13 novos testes (167 no total).

### Fixed

- **Dedup por linha → por problema** (review): relatório de research com várias
  oportunidades perdia todas exceto a primeira (`ref = research:{id}`); agora
  `research:{id}:{slug(problema)}` (SPEC-034 R2).
- **Score stale** (review): `update_components` invalidava a pontuação cacheada
  (score/score_method/breakdown → NULL) — mudança de componente sempre recomputa;
  regressão cobre `score ice → update impact → list` recomputa 3.92 → 4.9.

### Changed

- README (167 testes, features de growth), roadmap SPEC-034 ✅, catálogo de automações.

## [0.5.0] — 2026-08-11 — SEO Engine (SPEC-023)

### Added

- **SEO Engine** (SPEC-023): auditoria determinística sobre o que o GEOS conhece
  (sem crawl web, sem dados de tráfego — nunca fabrica sinais):
  - **Docs**: broken links internos (`[text](path)` com resolução relativa `./`/`../`,
    âncoras e externos ignorados), documentos órfãos, thin content (< 40 palavras),
    metadados (sem título / primeira linha sem H1), falta de internal links.
  - **Content**: gaps (nós TOPIC do graph sem objeto de conteúdo → sugestão
    `geos content create`), cannibalização de tópicos, decay heurístico local
    (idade + nunca atualizado + corpo curto → proposta de refresh, honesta).
- **Migration V5** (`seo_engine`): tabelas `seo_audits` (snapshot por run) +
  `seo_issues` (severidade/categoria/alvo/detalhe/recomendação) — histórico.
- **CLI**: `geos seo audit [--scope docs|content] [--verbose]` e
  `geos seo issues [--severity]`.
- 9 novos testes (152 no total).

### Changed

- README atualizado (152 testes, features de SEO). Roadmap: SPEC-023 ✅ IMPLEMENTED.

## [0.4.0] — 2026-08-11 — Model Providers (SPEC-039)

### Added

- **ModelProvider** (spec §35 / SPEC-039): protocolo `complete(system, user, …)` →
  `ModelResponse(text, model, provider, finish_reason, usage, latency_ms, mock)`;
  `OpenAICompatibleModelProvider` com stdlib `urllib` (zero deps; OpenAI, Azure,
  vLLM/Ollama locais; chave via `GEOS_OPENAI_API_KEY`/`OPENAI_API_KEY`); factory
  `provider_from_config` lendo a seção `models` do `geos.yaml`.
- **Síntese real do ResearchEngine**: com provider configurado, a síntese é gerada
  por LLM **estritamente ancorada nas fontes recuperadas** (regras anti-alucinação +
  citações [F#]); linha registra `model`/`provider`/`mock` (migration V4, aditiva).
  Sem provider (default), nada muda — síntese mock determinística.
- **CLI**: `geos models info` (config) e `geos models test` (conectividade live).
- Migration V4 (`model_provenance`): `ALTER TABLE research ADD COLUMN model/provider/
mock` — segura em bancos existentes com dados.

### Fixed

- Fallback honesto mesmo quando o provider retorna **texto vazio** (regressão: o raise
  fora do try derrubava o research inteiro; agora cai para o mock — SPEC-039 R3).
- `http.client.IncompleteRead`/`BadStatusLine` (HTTPException) e `KeyError` em shape
  malformado agora viram `ModelError` tipado — nenhuma exceção crua escapa.

### Changed

- README atualizado (143 testes, features de modelos). `geos.yaml` default documenta a
  seção `models` comentada.

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
