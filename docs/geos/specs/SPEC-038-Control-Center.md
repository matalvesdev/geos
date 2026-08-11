# SPEC-038 — Control Center

> **State: CURRENT** · Status: IMPLEMENTED + TESTED (bootstrap) · Phase: 5 · Version: 1

## Objetivo

Dashboard **estático e autocontido** do workspace — `geos control-center build`
gera um único `control-center.html` (dark theme, zero assets externos, charts em
CSS puro, sem JavaScript) com o estado determinístico do GEOS no momento do build:
KPIs, insights, distribuição, aprovações pendentes, saúde, runs recentes e o
último snapshot de métricas.

## Escopo (bootstrap)

- **KPIs**: docs ingeridos, conteúdo (aprovado/publicado), blog, social,
  oportunidades, experimentos.
- **Insights**: os insights persistidos do SPEC-035 (OBSERVATION / HYPOTHESIS /
  INVESTIGATION) com evidência.
- **Distribuição**: barras de conteúdo publicado, aguardando aprovação e SEO
  issues críticas.
- **Aprovações pendentes** (action, risk) e **saúde** (schema, knowledge,
  approvals) e **runs recentes** (workflow, status, início).
- **Métricas do último snapshot** (SPEC-035) em tabela.

## Fora de escopo (fases futuras)

- Servidor/watch (hot reload) — o HTML é estático por design (local-first,
  versionável, abrível de qualquer lugar).
- RAG debugger, agent-run debugger, backups, self-audit UI — roadmap fase 5.
- Charts interativos (JS) — mantidos em CSS puro por determinismo e portabilidade.

## Requisitos-chave

- R1: **autocontido** — um único arquivo HTML, sem CDN, sem JS, abre via
  `file://` e funciona offline.
- R2: **determinístico** — mesmo estado → mesmo HTML (exceto timestamp).
- R3: **read-only** — nunca modifica o banco; snapshot do momento do build.

## Aceitação

- `tests/test_bootstrap.py::ControlCenterTests`: HTML gerado com `GEOS`,
  `SPEC-038`, `<style>` e sem `<script>`; com snapshot de analytics mostra
  métricas e insights.
- Smoke real: `geos bootstrap` → `geos analytics collect` →
  `geos control-center build` → abrir no navegador (verificado: KPIs, insights,
  tabela, zero console errors).
