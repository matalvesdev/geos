# SPEC-024 — Blog Publisher

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 2 · Version: 1

## Objetivo

Motor de publicação de blog (spec master §75–77) que transforma objetos de conteúdo
**aprovados** (SPEC-022) em posts publicáveis — markdown com front matter — e os
escreve em um destino através de **adapters** (local headless por default; WordPress,
Ghost e CMS custom em fases futuras). Toda publicação é **gated por aprovação humana**
(SPEC §47: `blog.publish` = HUMAN_APPROVAL_REQUIRED) e registrada em `blog_posts` para
auditoria.

## Escopo (bootstrap)

- **Preparação** (`blog prepare`): a partir de um objeto de conteúdo em status
  `APPROVED` (ou `SCHEDULED`), gera o post markdown completo:
  - Front matter YAML determinístico: `title`, `slug`, `date`, `type`, `status`,
    `keywords`, `summary` (primeira linha do body), `sources`, `mock` (honesto).
  - Body: o corpo do objeto de conteúdo + rodapé de proveniência
    (content id, versão, fonte) — nunca fabrica conteúdo novo.
- **Publicação** (`blog publish`):
  - Sem aprovação: cria um approval `blog.publish` PENDING e marca o post
    `APPROVAL_PENDING` — nada externo acontece (SPEC §47).
  - Com aprovação (`--approve`): decide o approval, escreve o arquivo via adapter,
    marca `PUBLISHED`, registra `published_path`/`published_at` e publica o evento
    `blog.published`.
- **Adapters**: protocolo `BlogAdapter.publish(post) -> BlogPublishResult`; registro
  por nome (`local` por default). `LocalMarkdownAdapter` escreve `<slug>.md` em um
  diretório configurável (default `blog/` do workspace).
- **Persistência**: tabela `blog_posts` (migration V7) — status
  `DRAFT → APPROVAL_PENDING → PUBLISHED` (+ `FAILED` em erro de adapter).
- **CLI**: `geos blog prepare/list/publish`.

## Fora de escopo (fases futuras / adapters web)

- CMS remoto (WordPress REST, Ghost Content API, custom) — o protocolo `BlogAdapter`
  já permite; o adapter local é o único implementado.
- Rendering HTML/sitemap/feed — fica para o CMS/site.
- Agendamento real (`SCHEDULED` → publish automático) — o publish segue manual/aprovado.

## Requisitos-chave

- R1: **aprovação humana obrigatória** antes de qualquer escrita externa — sem
  `--approve` (ou approval decidido), o publish nunca toca o sistema de arquivos.
- R2: front matter e markdown são **determinísticos**; `mock` reflete o objeto de
  conteúdo (nunca omite que é rascunho de template).
- R3: publish é **idempotente por post** (um post publica uma vez; republicar falha
  com `BlogError` até haver suporte a versões de publicação).
- R4: proveniência preservada: front matter registra content_id, versão e fontes;
  a linha `blog_posts.content_id` liga ao objeto de conteúdo.
- R5: integração com Content Engine — o publish **não** altera o status do objeto de
  conteúdo automaticamente (decisão humana separada via `content status`).

## Aceitação

- `tests/test_blog.py` (~12 testes): prepare (valida status, front matter, body),
  publish gated (approval PENDING sem `--approve`), publish aprovado (arquivo markdown
  escrito com front matter + evento), idempotência, adapter registry, CLI.
- Smoke real no workspace: `geos blog prepare` + `blog publish --approve` sobre um
  conteúdo aprovado.
