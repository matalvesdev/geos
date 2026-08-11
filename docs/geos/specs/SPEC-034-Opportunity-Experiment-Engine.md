# SPEC-034 — Opportunity & Experiment Engine

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 2 · Version: 1

## Objetivo

Conectar a descoberta (research + SEO) à ação mensurável: insights viram
**oportunidades priorizadas** (ICE/RICE explicáveis, spec §102) e oportunidades viram
**experimentos** com hipótese, métricas, guardrails, resultado e aprendizado (spec §101,
§105). Score auxilia, nunca substitui julgamento.

## Escopo

- **Opportunity** (spec §59): problem, audience, evidence, impact, confidence, effort,
  strategic_alignment, recommended_action, score + breakdown, status.
- **Scoring**: ICE (Impact × Confidence × Ease / 100) e RICE (Reach × Impact ×
  Confidence / Effort) — determinísticos, com breakdown por componente e razões
  (nunca apenas um número, analogia SPEC §114).
- **Coleta automática**: insights de research (`CONTENT_OPPORTUNITY`/`KNOWLEDGE_GAP`)
  e gaps de SEO (tópicos sem conteúdo) → oportunidades com evidência (research_id /
  nó do graph).
- **Experiment** (spec §101): problem, evidence, hypothesis, change, audience,
  primary_metric, secondary_metrics[], guardrails[], expected_impact, confidence,
  effort, status (PROPOSED → RUNNING → COMPLETED), result, analysis, decision
  (ADOPT | REJECT | ITERATE), learning. Aprendizado sempre registrado.
- **CLI**: `geos opportunities collect/list`, `geos experiments create/list/complete`.
- Persistência: migration V6 (`opportunities`, `experiments`).

## Fora de escopo

- Execução de experimentos em canais externos (só registro + decisão).
- Analytics de resultados (SPEC-035) — `complete` aceita o resultado informado.

## Requisitos-chave

- R1: scoring é determinístico e explicável (breakdown + confidence honesta).
- R2: toda oportunidade tem evidência (research_id, uri do SEO gap, ou "manual").
- R3: experimento só nasce de uma oportunidade (rastreabilidade).
- R4: `complete` exige resultado + decisão + learning (nunca vazio).
- R5: `NO ACTION` continua sendo resultado válido (spec §119) — oportunidades podem
  ser arquivadas sem experimento.

## Aceitação

- `tests/test_growth.py` (~15 testes): matemática ICE/RICE com entradas conhecidas,
  collect de research+SEO, dedup, lifecycle do experimento, R4, CLI.
- Smoke real na Zetra: `geos opportunities collect` + `list --method rice` + um
  experimento completo de ponta a ponta.
