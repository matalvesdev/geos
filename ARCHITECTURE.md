# Architecture

Visão completa: [`docs/geos/architecture/vision.md`](docs/geos/architecture/vision.md).
Decisões: [`docs/geos/adrs/`](docs/geos/adrs/) (GEOS-ADR-0001..0006).

## Em uma frase

GEOS é uma **plataforma agentic de crescimento organizacional** que converte
`SIGNALS → RESEARCH → KNOWLEDGE → STRATEGY → CONTENT → DISTRIBUTION → LEADS →
QUALIFICATION → MEETINGS → OPPORTUNITIES → CUSTOMERS → EDUCATION → COMMUNITY →
ANALYTICS → LEARNING` em um ciclo contínuo e mensurável — local-first, com
aprovação humana em todo risco externo.

## Camadas

```
CLI / API                          ← Control Plane
Workflow Engine · Agent Runtime · Policy/Approval
Event Bus · Job Queue · Scheduler
Intelligence Layer (Knowledge): SQLite (SQL+FTS) · Retrieval (RAG) · Graph
Domain layers (research, content, seo, leads, crm, meetings, academy, community, analytics)
Action Gateway (approvals) → Integrations (search, calendar, email, social, cms, crm…)
```

## Princípios estruturais

- **SQLite-first**, storage atrás de repositórios (nenhum domínio toca SQLite
  diretamente; PostgreSQL/vector/graph são providers futuros) — ADR-0002.
- **Bus/queue em processo** com protocolos para adapters (Kafka/RabbitMQ/Celery…)
  — ADR-0003.
- **Determinístico primeiro, LLM por último** (cron, FTS, scoring, dedup, detecção
  são código puro) — ADR-0004.
- **Não-destrutivo em brownfield**: `geos init` só escreve `.geos/` e `docs/geos/`;
  shadow mode + feature flags antes de automação externa — ADR-0005.
- **Sem god agent**: agentes especializados; colaboração sempre com budget/exit
  conditions.

## Repositório

```
geos/
├── geos/          # pacote Python (core, storage, intelligence, discovery, cli)
├── tests/         # unittest (zero deps além de PyYAML)
├── docs/geos/     # auditoria, contexto, visão, ADRs, roadmap, SPEC-001..010
├── workflows/     # workflows declarativos de exemplo
├── examples/      # quickstart
└── .github/       # CI
```

## Segurança

Condições de workflow via AST whitelist (sem eval); SQL parametrizado; FTS sanitizado;
secret-free por construção; política de aprovação declarativa (`geos.yaml`).
