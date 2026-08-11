# SPEC-023 — SEO Engine

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 2 · Version: 1

## Objetivo

Motor de SEO determinístico (spec master §80–83) que audita o que o GEOS conhece —
documentos ingeridos, objetos de conteúdo e knowledge graph — sem depender de crawl
web nem de dados de tráfego. Tudo persistido para histórico e comparação entre runs.

## Escopo (bootstrap)

- **Auditoria de documentos** (markdown ingerido):
  - Broken links: links internos `[text](path)` cujo alvo não existe entre os
    documentos ingeridos (normalização `./`/`../`, semântica de diretório).
  - Órfãos: documentos que nunca são apontados por nenhum link interno.
  - Thin content: documentos muito curtos (abaixo de um limite de palavras).
  - Metadados: título ausente ou primeira linha sem heading.
  - Internal linking: documentos sem nenhum link interno de saída.
- **Auditoria de conteúdo** (tabela `content`):
  - Gaps: tópicos presentes no knowledge graph (TOPIC) sem objeto de conteúdo.
  - Cannibalization: objetos de conteúdo compartilhando o mesmo tópico/headline.
  - Decay heurístico (§83): sinais locais — conteúdo antigo (idade), thin, sem links
    internos, sem atualização — → proposta de refresh (nunca causalidade de tráfego).
- **Persistência**: `seo_audits` (resumo por run) + `seo_issues` (itens com severidade,
  categoria, alvo, detalhe, recomendação).
- **CLI**: `geos seo audit` e `geos seo issues`.

## Fora de escopo (fases futuras / adapters web)

- sitemap/robots/canonical/structured data/Core Web Vitals (requer site real via
  adapters web), keyword research com volume externo, SERP tracking.

## Severidades

- `critical`: broken link, órfão sem nenhum caminho de entrada.
- `warning`: thin content, cannibalization, decay alto.
- `info`: falta de internal links, gap de conteúdo, metadados incompletos.

## Requisitos-chave

- R1: audit é determinístico e idempotente (cada run grava um novo snapshot; nunca
  fabrica dados de tráfego).
- R2: recomendações são ações concretas (link a criar, conteúdo a criar, refresh),
  com o alvo identificado (uri/slug/tópico).
- R3: nenhuma ação externa — audit é read-only (SPEC §47: SAFE_AUTOMATIC).
- R4: integração com Content Engine: `seo opportunities` lista gaps que podem virar
  `content create` (decisão humana).

## Aceitação

- `tests/test_seo.py` (~15 testes): links quebrados/órfãos/thin/metadados/gaps/
  cannibalization/decay, persistência e CLI.
- Smoke real no workspace Zetra: `geos seo audit` + `geos seo issues`.
