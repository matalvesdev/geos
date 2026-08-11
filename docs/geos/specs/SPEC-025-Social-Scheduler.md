# SPEC-025 — Social Scheduler

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 2 · Version: 1

## Objetivo

Agendador social (spec master §78–79) que transforma conteúdo **aprovado** (SPEC-022)
em posts determinísticos por canal — texto derivado do body (hook + excerto), hashtags
das keywords, CTA quando presente — truncados honestamente ao limite de cada canal. A
publicação é **gated por aprovação humana** (SPEC §47: `social.publish` =
HUMAN_APPROVAL_REQUIRED) e registrada em `social_posts` para auditoria. Post pode ser
**agendado** (SCHEDULED) e o engine expõe os vencidos (`due`) para automação futura —
mas a escrita externa sempre exige publish aprovado.

## Escopo (bootstrap)

- **Canais determinísticos**: `x` (280), `linkedin` (3000), `bluesky` (300),
  `instagram` (2200) — limites honestos em `CHANNELS`.
- **Preparação** (`social prepare`): de um objeto de conteúdo em `APPROVED`/`SCHEDULED`,
  gera o post:
  - Hook: primeira linha significativa do body (ou título) — nunca fabrica conteúdo.
  - Excerto: linhas restantes do body, truncado com "…" quando exceder o limite
    (flag `truncated` honesta no evento `social.prepared`).
  - Hashtags: keywords slugificadas (acentos normalizados), deduplicadas, máx. 5.
  - CTA: campo `cta` do objeto de conteúdo, quando presente.
  - Agendamento opcional (`--at`): registra `scheduled_at` (janela de publicação).
- **Publicação** (`social publish`):
  - Sem aprovação: cria approval `social.publish` PENDING e marca `APPROVAL_PENDING` —
    nada externo acontece (SPEC §47).
  - Com aprovação (`--approve`): se `scheduled_at` futuro → `SCHEDULED` (fila, nada
    externo); caso contrário decide o approval, escreve via adapter, marca `PUBLISHED`
    e publica `social.published`.
- **Adapters**: protocolo `SocialAdapter.publish(post) -> SocialPublishResult`;
  `LocalSocialAdapter` escreve `<channel>-<slug>.txt` em diretório configurável
  (default `social/` do workspace). X/LinkedIn/Bluesky/Instagram APIs ficam em fases
  futuras atrás do mesmo protocolo.
- **Persistência**: tabela `social_posts` (migration V8) — status
  `DRAFT → APPROVAL_PENDING → SCHEDULED/PUBLISHED` (+ `FAILED` em erro de adapter),
  índice único (content_id, channel) — um post por conteúdo por canal.
- **CLI**: `geos social prepare/list/due/publish`.

## Fora de escopo (fases futuras)

- Adapters reais por canal (X API, LinkedIn API, Bluesky, Instagram) — protocolo pronto.
- Publicação automática no horário (worker/scheduler real) — `due` expõe os vencidos;
  a escrita continua exigindo publish aprovado.
- Media/anexos (imagens, carrossel, vídeo) — posts de texto apenas no bootstrap.

## Requisitos-chave

- R1: **aprovação humana obrigatória** antes de qualquer escrita externa — sem
  `--approve` (ou approval decidido), o publish nunca toca o sistema de arquivos.
- R2: posts são **determinísticos** por (conteúdo, canal) e **nunca excedem** o limite
  do canal; truncamento é honesto (marcado, nunca silencioso).
- R3: publish é **idempotente por post** (um post publica uma vez; republicar falha
  com `SocialError`).
- R4: **agendamento** registra a janela (`scheduled_at`); post agendado aprovado fica
  `SCHEDULED` (nada externo até o horário); `due` lista os vencidos.
- R5: proveniência preservada: `content_id` liga ao objeto de conteúdo; rodapé no
  arquivo registra content, post, canal e SPEC-025.

## Aceitação

- `tests/test_social.py` (25 testes): limites por canal, truncamento honesto, hashtags
  (dedup/limite/acentos), prepare (status, body, duplicidade por content+canal,
  re-prepare de FAILED),
  publish gated (approval PENDING sem `--approve`), reuso de approval pendente, decisão
  só após escrita bem-sucedida, agendamento (SCHEDULED sem escrita, `due`, publish pós-
  vencimento), idempotência, adapter registry, CLI.
- Smoke real no workspace: `geos content create/draft/status` → `social prepare --channel x`
  → `social publish` (gated) → `social publish --approve` (escreve `social/x-<slug>.txt`).
