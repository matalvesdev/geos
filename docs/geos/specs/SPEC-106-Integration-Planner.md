# SPEC-106 — Integration Planner

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 0 (mandated adoption) · Version: 1

## Objetivo

`geos plan` (SPEC-106) produz um **plano de integração determinístico** a partir
do manifest (mode, capabilities) + estado local (docs, content, blog, social,
automações) — um roteiro em fases que mostra exatamente o que rodar para
evoluir o workspace, sempre respeitando ADR-0005 (shadow mode + aprovação
humana antes de qualquer ação externa).

## Escopo (bootstrap)

- **Fases determinísticas** (5): Fundamentos → Conhecimento & Research →
  Conteúdo → Distribuição (aprovação obrigatória) → Crescimento & Medição.
- **Estado local exibido**: docs ingeridos, conteúdo, blog, social, automações
  registradas — o plano reflete o que já existe.
- **Princípio explícito**: nenhuma automação externa sem shadow mode/approval;
  nada documentado sem estar implementado.

## Fora de escopo

- Execução automática dos passos — `plan` é read-only (recomenda, não executa).
- Plano por capacidade individual (REUSE/INTEGRATE/CREATE) — mantido o mapeamento
  no `capability_actions` para futuras fases de adoção por domínio.

## Requisitos-chave

- R1: plano é **determinístico** — mesmo workspace → mesmo plano.
- R2: **read-only** — nunca modifica arquivos, banco ou config.
- R3: reflete o **estado real** (docs/content/social/automações contados do banco).

## Aceitação

- `tests/test_cli.py::test_plan_spec_106`: plan imprime fases (Fundamentos,
  Crescimento) e estado local em workspace BROWNFIELD simulado.
- Smoke real: `geos bootstrap` → `geos plan` mostra as 5 fases.
