# GEOS — Growth, Education & Organizational System

> Open-source · local-first · agentic organizational growth platform

[![CI](https://github.com/matalvesdev/geos/actions/workflows/ci.yml/badge.svg)](https://github.com/matalvesdev/geos/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://github.com/matalvesdev/geos/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/geos.svg?logo=pypi&logoColor=white)](https://pypi.org/project/geos/)
[![Tests](https://img.shields.io/badge/tests-143%20passing-green)](https://github.com/matalvesdev/geos/actions/workflows/ci.yml)

**GEOS** é uma plataforma agentic que transforma sinais de mercado em inteligência
organizacional e ação coordenada — de forma mensurável e com supervisão humana em todo
risco externo.

```
SIGNALS → RESEARCH → KNOWLEDGE → STRATEGY → CONTENT → DISTRIBUTION → LEADS →
QUALIFICATION → MEETINGS → OPPORTUNITIES → CUSTOMERS → EDUCATION → COMMUNITY →
ANALYTICS → LEARNING → (melhor conhecimento, estratégia, produto, distribuição)
```

## Features

- **Core agentic**: agentes declarativos (YAML), workflows com aprovação, jobs com retry
  e dead-letter, scheduler cron/intervalo (parser próprio), event bus persistido.
- **Conhecimento local**: ingestão de Markdown com dedup por hash, chunking por headings,
  busca FTS5, embeddings locais determinísticos, **hybrid RAG** (FTS + vetores + graph
  boost) com citações e proveniência.
- **Knowledge Graph**: extração determinística de entidades (companhias, produtos, tópicos,
  problemas) + relações `discusses`/`relates_to` em SQLite.
- **Research Engine**: pipeline QUESTION → SOURCES → SYNTHESIS → INSIGHTS sobre o índice
  local (nunca inventa fontes; síntese marcada `mock` até existir ModelProvider).
- **Content Engine**: objetos de conteúdo tipados (18 tipos), scoring determinístico e
  explicável, pipeline de status validado (IDEA → … → PUBLISHED) com versionamento,
  repurposing determinístico — CLI `geos content`.
- **Embeddings plugáveis**: local determinístico (hash) por padrão ou OpenAI-compatible
  (OpenAI/Azure/vLLM/Ollama) via `knowledge.embeddings` — mesmo protocolo, zero deps.
- **ModelProvider** (spec §35): protocolo único para LLMs (OpenAI-compatible, local ou
  nuvem); síntese do research gerada por modelo **ancorada nas fontes com citações
  [F#]** quando `models:` está configurado — fallback mock honesto sem config.
- **Memory**: memória persistente com TTL/sensibilidade e scopes por domínio.
- **Adoção não-destrutiva**: detecção GREENFIELD/BROWNFIELD/STANDALONE com evidências,
  capability discovery por repo, manifest e Repository Registry.
- **SQLite-first, zero infra obrigatória**: nada de Kafka/Redis/Postgres para rodar o
  primeiro workflow; protocolos para trocar storage/LLM/embeddings depois.

## O que é (e o que não é)

| GEOS é | GEOS não é |
|---|---|
| Sistema operacional de marketing/growth | Content farm ou gerador de posts |
| Motor de experimentação de crescimento | Spam engine / cold-outreach em massa |
| Sistema de conhecimento + RAG | Chatbot ou coleção de prompts |
| Framework de agentes especializados | Swarm não controlado ou god agent |
| Camada de orquestração de CRM/leads | Substituição de stack existente |

## Por que GEOS

- **Local-first**: SQLite + bus em processo. Nada de Kafka/Redis/Postgres obrigatório
  para o primeiro workflow.
- **Determinístico primeiro, LLM por último**: cron, FTS, scoring, dedup e detecção
  são código puro.
- **Aprovação humana** para ações externas (publish, social, newsletter, meetings…).
- **BROWNFIELD não-destrutivo**: instala em projetos existentes sem modificar o código
  do produto; reusa infra (banco, fila, CI) via adapters.
- **Spec-Driven Development**: nada é documentado como existente sem estar implementado.

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

Sem `pip install`? `python -m geos.cli ...` funciona igual.

## Repositório

```
geos/
├── geos/          # pacote Python (core, storage, intelligence, discovery, cli)
├── tests/         # unittest (zero deps além de PyYAML) — 143 testes
├── docs/geos/     # auditoria, contexto, visão, ADRs, roadmap, SPEC-001..022, 039
├── workflows/     # workflows declarativos de exemplo
├── examples/      # quickstart + config + docs de exemplo
└── .github/       # CI (Linux + Windows, Python 3.11–3.13)
```

## Documentação

- **Arquitetura** → [ARCHITECTURE.md](ARCHITECTURE.md) · visão completa em
  [docs/geos/architecture/vision.md](docs/geos/architecture/vision.md)
- **Roadmap** → [ROADMAP.md](ROADMAP.md) · detalhado em
  [docs/geos/roadmaps/roadmap.md](docs/geos/roadmaps/roadmap.md)
- **Specs** → [docs/geos/specs/](docs/geos/specs/) (SPEC-001..022 implementadas)
- **Decisões (ADRs)** → [docs/geos/adrs/](docs/geos/adrs/)

## Desenvolvimento

```bash
python -m unittest discover -s tests -t .   # 143 testes, stdlib
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
