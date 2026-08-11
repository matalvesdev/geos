# SPEC-103 — Greenfield Bootstrap

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 0 (mandated adoption) · Version: 1

## Objetivo

Transforma um diretório vazio em um workspace GEOS **funcional** com um único
comando (`geos bootstrap`) — config, workflows de exemplo, docs de exemplo
ingeridos como conhecimento, banco migrado, conteúdo seed aprovado e
automações padrão registradas. Idempotente e local-first: nada externo é tocado.

## Escopo (bootstrap)

- **Scaffold**: `workflows/` (4 workflows de exemplo do pacote), `examples/docs/`
  (3 docs de demonstração), `geos.yaml` + manifest (reuso da lógica do `init`).
- **Base de conhecimento**: ingestão dos docs de exemplo (chunks + FTS +
  embeddings hash) — `geos knowledge search` funciona imediatamente.
- **Pipeline de conteúdo**: um item seed `Cash application na prática` criado,
  briefed, draftado e **APROVADO** (idempotente — reusa em re-runs).
- **Automações padrão** (SPEC-006): `daily-intelligence`, `social-worker`,
  `analytics-collect`, `opportunities-collect`, `seo-audit` persistidas em
  `.geos/automations.json` com `next_run` — prontas para `geos automations run`.
- **Próximos passos** impressos (workflows list, knowledge search, analytics).

## Fora de escopo

- Automações reais em produção — o worker permanece manual
  (`geos automations run`); a execução externa continua approval-gated.
- Template customizado de workspace (dirs/regras por projeto) — fase futura.

## Requisitos-chave

- R1: **idempotente** — re-runs não duplicam workflows, docs, automações nem seed.
- R2: **local-first** — nenhuma escrita externa, nenhuma credencial necessária.
- R3: o workspace resultante roda `doctor`, `search`, `content`, `analytics` e
  `automations list` sem configuração adicional.

## Aceitação

- `tests/test_bootstrap.py` (BootstrapTests): workspace funcional (workflows,
  docs, seed, search, automações persistidas) e idempotência (re-run não duplica).
- Smoke real: `geos bootstrap` em diretório vazio → comandos do checklist OK.
