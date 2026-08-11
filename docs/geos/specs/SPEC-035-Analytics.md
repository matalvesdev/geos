# SPEC-035 — Analytics

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 2 · Version: 1

## Objetivo

Motor de analytics determinístico (spec master §analytics) que computa métricas
**exclusivamente sobre o que o GEOS já conhece** — content, blog, social, SEO,
growth, research, telemetry — e as transforma em insights acionáveis
(OBSERVATION / HYPOTHESIS / INVESTIGATION). Nunca fabrica dados nem busca
sinais externos: cada métrica é uma função determinística sobre o banco local,
e cada insight carrega evidência + confiança honesta.

## Escopo (bootstrap)

- **MetricRegistry**: ~22 métricas por domínio (content, blog, social, seo,
  growth, research, telemetry), cada uma com nome, domínio, descrição honesta e
  função determinística (`COUNT`/`AVG` sobre tabelas locais). Uma métrica que
  falhar nunca derruba o run (registra `None` e segue).
- **Snapshot persistido** (migration V9): tabelas `metric_snapshots` (métricas +
  summary JSON por run) e `analytics_insights` (tipo, severidade, conteúdo,
  evidência, confiança) — histórico completo.
- **Insights determinísticos por regra**:
  - `OBSERVATION` — fato (ex.: "N posts aguardam aprovação humana", "sem
    pendências — operação limpa").
  - `INVESTIGATION` — algo a seguir (ex.: posts sociais agendados vencidos,
    issues críticas de SEO, taxa de falha de workflows ≥ 10%).
  - `HYPOTHESIS` — testável, com `confidence` baixa honesta (ex.: publicações
    sociais podem gerar tráfego — a medir quando houver métricas reais).
- **CLI**: `geos analytics collect` (snapshot + insights),
  `geos analytics metrics [--domain]`, `geos analytics insights [--type]`.

## Fora de escopo (fases futuras)

- AnalyticsProvider com dados externos (GA4, Search Console, métricas de canal)
  — protocolo fica para quando houver integrações reais.
- Dashboard/UI — o Control Center (SPEC-038) consumirá os snapshots.
- Alertas/recomendações proativas — o loop self-improvement (fase 5).

## Requisitos-chave

- R1: métricas são **determinísticas e honestas** — nada de estimativa, nada de
  dado externo; proveniência é o próprio banco local.
- R2: insights são **baseados em evidência** (campo `evidence` sempre presente)
  e `HYPOTHESIS` nunca reivindica confiança alta (≤ 0.3 no bootstrap).
- R3: snapshot é **imutável e histórico** — cada `collect` adiciona, nunca
  sobrescreve; `insights` filtráveis por tipo.
- R4: falha isolada de uma métrica não falha o run (registra `None`).

## Aceitação

- `tests/test_analytics.py` (8 testes): coleta retorna métricas + insights,
  métricas refletem estado local (content APPROVED/PUBLISHED), pendências de
  aprovação geram OBSERVATION, `social_due` gera INVESTIGATION, persistência +
  filtro por tipo, filtro por domínio, erro antes do primeiro snapshot,
  operação limpa → observação "sem pendências".
- Smoke real: `geos analytics collect` + `geos analytics metrics --domain social`.
