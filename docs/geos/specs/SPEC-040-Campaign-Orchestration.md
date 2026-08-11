# SPEC-040 — Campaign Orchestration

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 2 · Version: 1

## Objetivo

Orquestrar esforços de crescimento em **campanhas coordenadas** que conectam
conteúdo, distribuição social e experimentos a um objetivo mensurável. Cada
campanha tem uma hipótese, público-alvo, cronograma, orçamento e KPIs
rastreáveis. O engine gerencia o lifecycle completo (PLANNED → ACTIVE →
PAUSED → COMPLETED / CANCELLED) e fornece linking idempotente, métricas
persistidas e tracking de orçamento.

## Escopo

- **Campaign** (spec §campaigns): name, slug, campaign_type, hypothesis,
  objective, audience, budget, total_spend, start_date, end_date,
  target_metrics (JSON), tags, status, result, cancel_reason.
- **Campaign Types**: `content_distribution`, `lead_generation`,
  `brand_awareness`, `product_launch`, `community_building`, `education`,
  `retention`, `event`.
- **Lifecycle** (deterministic transitions):
  - `PLANNED → ACTIVE | CANCELLED`
  - `ACTIVE → PAUSED | COMPLETED | CANCELLED`
  - `PAUSED → ACTIVE | CANCELLED`
  - `COMPLETED` e `CANCELLED` são terminais.
- **Content Linking** (junction table `campaign_content`): idempotent
  add/remove/list operations connecting campaigns to content items.
- **Social Linking** (junction table `campaign_social`): idempotent
  add/remove/list operations connecting campaigns to social posts.
- **Experiment Linking** (junction table `campaign_experiments`): idempotent
  add/remove/list operations connecting campaigns to experiments.
- **Metrics Tracking** (table `campaign_metrics`): record metric values with
  name, value, source, and timestamp; get metrics with latest/sum/count per
  metric name; get summary with progress vs targets.
- **Budget Tracking** (table `campaign_spends`): record spends against budget
  with validation; get budget status with utilization percentage.
- **CLI**: `geos campaigns create/list/show/activate/pause/complete/cancel`,
  `add-content/add-social/add-experiment`, `record-metric/record-spend/summary`.
- Persistência: migration V10 (`campaigns`, `campaign_content`, `campaign_social`,
  `campaign_experiments`, `campaign_metrics`, `campaign_spends`).

## Fora de escopo

- Execução automática de campanhas em canais externos (só registro + lifecycle).
- Analytics avançado de campanhas (SPEC-035 consome métricas quando disponíveis).
- Multi-campanha scheduling automático (automação futura).

## Requisitos-chave

- R1: lifecycle é **determinístico e validado** — transições ilegais falham
  com `CampaignError` (nunca permite saltar status).
- R2: linking de conteúdo/social/experimentos é **idempotente** — adicionar
  o mesmo item duas vezes não cria duplicatas.
- R3: métricas são **persistidas com histórico** — cada registro é imutável;
  `get_metrics` retorna latest/sum/count por nome.
- R4: orçamento é **validado** — spend que excede budget levanta
  `CampaignError` (nunca permite ultrapassar).
- R5: campanhas terminais (`COMPLETED`/`CANCELLED`) **não aceitam transições**
  — lifecycle é finite e acíclico.

## Arquitetura

```
CampaignEngine (domains/campaigns.py)
├── create / get / list
├── activate / pause / complete / cancel (lifecycle)
├── add_content / remove_content / list_content
├── add_social_post / remove_social_post / list_social_posts
├── add_experiment / remove_experiment / list_experiments
├── record_metric / get_metrics / get_metric_summary
├── record_spend / get_budget_status
└── summary

CampaignRepository (storage/repos.py)
├── CRUD campaigns
├── junction: campaign_content, campaign_social, campaign_experiments
├── metrics: campaign_metrics (append-only)
└── spends: campaign_spends + total_spend rollup

Migration V10 (storage/migrations.py)
├── campaigns (id, name, slug, type, status, budget, ...)
├── campaign_content (campaign_id, content_id)
├── campaign_social (campaign_id, post_id)
├── campaign_experiments (campaign_id, experiment_id)
├── campaign_metrics (id, campaign_id, metric_name, value, source, recorded_at)
└── campaign_spends (id, campaign_id, amount, description, recorded_at)
```

## Aceitação

- `tests/test_campaigns.py` (21 testes):
  - CRUD básico (create, get, list, empty name, invalid type)
  - Lifecycle transitions (PLANNED→ACTIVE→PAUSED→COMPLETED, CANCELLED)
  - Transições ilegais falham com CampaignError
  - Content linking (add, remove, idempotent duplicate)
  - Metrics tracking (record, latest, sum, count)
  - Budget tracking (record spend, validation, exceeded error)
  - Budget status (remaining, utilization)
  - Summary (campaign + content + social + experiments + metrics + budget)
- Smoke real: `geos campaigns create "Test" --budget 1000 && geos campaigns list`
