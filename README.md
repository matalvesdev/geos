# GEOS — Growth, Education & Organizational System

> Open-source · local-first · **AI agent framework for growth engineering**

[![CI](https://github.com/matalvesdev/geos/actions/workflows/ci.yml/badge.svg)](https://github.com/matalvesdev/geos/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://github.com/matalvesdev/geos/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/geos.svg?logo=pypi&logoColor=white)](https://pypi.org/project/geos/)
[![Tests](https://img.shields.io/badge/tests-333%20passing-green)](https://github.com/matalvesdev/geos/actions/workflows/ci.yml)

**GEOS** é um framework open-source de agentes de IA para growth engineering.

Ele orquestra agentes especializados — cada um com uma responsabilidade clara — que
trabalham juntos para transformar sinais de mercado em ação coordenada: pesquisa,
conhecimento, conteúdo, distribuição, leads, CRM, educação e analytics.

Tudo com supervisão humana em cada risco externo. Tudo local-first. Tudo determinístico
quando possível, LLM apenas quando necessário.

```
SIGNALS → RESEARCH → KNOWLEDGE → STRATEGY → CONTENT → DISTRIBUTION → LEADS →
QUALIFICATION → MEETINGS → OPPORTUNITIES → CUSTOMERS → EDUCATION → COMMUNITY →
ANALYTICS → LEARNING → (melhor conhecimento, estratégia, produto, distribuição)
```

## Arquitetura de Agentes

GEOS não é um "god agent" que faz tudo. É um **framework de agentes especializados**
que colaboram via event bus, workflows declarativos e filas de jobs:

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI / API                               │
├─────────────────────────────────────────────────────────────────┤
│              Workflow Engine · Agent Runtime · Policy            │
├─────────────────────────────────────────────────────────────────┤
│          Event Bus · Job Queue · Scheduler (cron/interval)      │
├─────────────────────────────────────────────────────────────────┤
│   Intelligence Layer: SQLite (SQL+FTS) · RAG · Knowledge Graph  │
├─────────────────────────────────────────────────────────────────┤
│  Research · Content · SEO · Leads · CRM · Meetings · Academy    │
│  Community · Analytics · Blog · Social · Campaigns · Email      │
├─────────────────────────────────────────────────────────────────┤
│       Action Gateway (approvals) → Integrations externas        │
└─────────────────────────────────────────────────────────────────┘
```

### Como os agentes colaboram

- **Agentes declarativos** (YAML) com roles, tasks e conditions
- **Workflows** orquestram a sequência de agentes com aprovação humana
- **Event bus** persistido conecta agentes de forma desacoplada
- **Job queue** com retry, backoff exponencial e dead-letter
- **Scheduler** cron/intervalo para automações agendadas
- **ModelProvider** protocolo único para LLMs (OpenAI-compatible, local ou nuvem)

### Princípios do framework

- **Determinístico primeiro, LLM por último**: cron, FTS, scoring, dedup e detecção são código puro
- **Aprovação humana obrigatória**: nenhuma ação externa sem supervisão
- **Agentes especializados**: cada agente tem uma responsabilidade clara (não um agente que faz tudo)
- **Zero infra obrigatória**: SQLite + bus em processo para rodar o primeiro workflow
- **Spec-Driven Development**: nada é documentado sem estar implementado

## Features

### Core Agentic

- **Agentes declarativos** (YAML) com roles, tasks e conditions
- **Workflows** com aprovação, retry e timeout
- **Job queue** SQLite com dead-letter e backoff exponencial
- **Scheduler** cron/intervalo (parser próprio, zero deps)
- **Event bus** persistido com protocolo para adapters externos
- **Memory** persistente com TTL, sensibilidade e scopes por domínio

### Intelligence Layer

- **Conhecimento local**: ingestão de Markdown com dedup por hash, chunking por headings, busca FTS5
- **Hybrid RAG**: FTS + vetores + graph boost com citações e proveniência
- **Knowledge Graph**: extração determinística de entidades + relações em SQLite
- **Embeddings plugáveis**: local determinístico (hash) ou OpenAI-compatible (OpenAI/Azure/vLLM/Ollama)
- **ModelProvider**: protocolo único para LLMs com síntese ancorada nas fontes e citações [F#]

### Growth Engines

- **Research Engine**: QUESTION → SOURCES → SYNTHESIS → INSIGHTS (nunca inventa fontes)
- **Content Engine**: 18 tipos, scoring explicável, pipeline IDEA → PUBLISHED com versionamento
- **SEO Engine**: auditoria determinística (broken links, órfãos, thin content, gaps, cannibalização)
- **Opportunity Engine**: coleta + scoring ICE/RICE com breakdown explicável
- **Experiment Engine**: lifecycle PROPOSED → RUNNING → COMPLETED com decisão ADOPT/REJECT/ITERATE

### Distribution & Outreach

- **Blog Publisher**: conteúdo aprovado → markdown com front matter, aprovação humana obrigatória
- **Social Scheduler**: posts por canal (X/LinkedIn/Bluesky/Instagram) com adapters reais de API
- **Social Worker L3**: executa apenas posts pré-aprovados por humano
- **Email Nurture**: sequences com triggers, enrollments, suppression list (no cold-spam)

### CRM & Leads

- **Lead Intelligence**: lifecycle CAPTURED → WON/LOST, scoring explicável, qualificação BANT/MEDDIC
- **CRM Pipeline**: deals com stages configuráveis, atividades, pipeline summary ponderado
- **Meeting Scheduling**: lifecycle SCHEDULED → COMPLETED/CANCELLED, analytics
- **Campaign Orchestration**: lifecycle PLANNED → COMPLETED, linking de conteúdo/social/experiments

### Education & Community

- **Academy**: tracks, courses, modules, lessons, labs, certifications, progress tracking
- **Community**: members multi-platform, threads, replies, analytics

### Observability

- **Analytics Engine**: ~22 métricas determinísticas + insights com evidência
- **Control Center**: dashboard HTML estático (dark theme, zero JS) com KPIs e health
- **RAG Debugger**: debug de queries com scoring e index stats
- **Run Debugger**: timeline de eventos por run
- **Self-Audit**: health checks automáticos com recomendações

## O que é (e o que não é)

| GEOS é | GEOS não é |
|---|---|
| Framework de agentes de IA para growth | Content farm ou gerador de posts |
| Sistema operacional de marketing/growth | Spam engine / cold-outreach em massa |
| Motor de experimentação de crescimento | Chatbot ou coleção de prompts |
| Sistema de conhecimento + RAG | Swarm não controlado ou god agent |
| Camada de orquestração de CRM/leads | Substituição de stack existente |

## Quickstart

```bash
git clone https://github.com/matalvesdev/geos.git
cd geos
python -m pip install -e .        # instala o entry point `geos`
geos init --mode greenfield       # detecta o modo (ou force greenfield)
geos db migrate
geos knowledge ingest examples/docs --source examples
geos knowledge search "origem de crédito"
geos workflows list
geos workflows run hello --input message="oi geos"
geos runs list
geos doctor
```

### Integrando em projeto existente (brownfield)

```bash
cd seu-projeto
geos init --mode brownfield       # não modifica código do produto
geos db migrate
geos knowledge ingest docs --source docs
geos analytics collect
geos cc audit                     # health check do workspace
```

Sem `pip install`? `python -m geos.cli ...` funciona igual.

## Repositório

```
geos/
├── geos/          # pacote Python (core, storage, intelligence, discovery, cli)
├── tests/         # unittest (zero deps além de PyYAML) — 333 testes
├── docs/geos/     # auditoria, contexto, visão, ADRs, roadmap, SPECs
├── workflows/     # workflows declarativos de exemplo
├── examples/      # quickstart + config + docs de exemplo
└── .github/       # CI (Linux + Windows, Python 3.11–3.13)
```

## Documentação

- **Arquitetura** → [ARCHITECTURE.md](ARCHITECTURE.md) · visão completa em
  [docs/geos/architecture/vision.md](docs/geos/architecture/vision.md)
- **Roadmap** → [ROADMAP.md](ROADMAP.md) · detalhado em
  [docs/geos/roadmaps/roadmap.md](docs/geos/roadmaps/roadmap.md)
- **Specs** → [docs/geos/specs/](docs/geos/specs/) (SPEC-001..025, 034, 035, 038, 039, 103, 106 implementadas)
- **Decisões (ADRs)** → [docs/geos/adrs/](docs/geos/adrs/)

## Desenvolvimento

```bash
python -m unittest discover -s tests -t .   # 333 testes, stdlib
python -m geos.cli doctor
```

Veja [CONTRIBUTING.md](CONTRIBUTING.md) (ciclo SDD, regras, PRs) e
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Segurança & privacidade

- Segredos nunca no repositório (`.env.example` apenas).
- Condições de workflow avaliadas por AST whitelist (sem `eval`).
- Política de aprovação declarativa; nenhuma automação externa sem supervisão.
- Vulnerabilidades: [SECURITY.md](SECURITY.md) / GitHub Private Vulnerability Reporting.

## Licença

[Apache-2.0](LICENSE) © 2026 Mateus Alves Bassane (Azeetra).
