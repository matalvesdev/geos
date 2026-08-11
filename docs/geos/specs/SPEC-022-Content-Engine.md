# SPEC-022 — Content Engine

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Phase: 2 · Version: 1

## Objetivo

Sistema de conteúdo com objeto tipado, scoring determinístico, pipeline com
transições validadas e repurposing — a base do content factory do GEOS
(spec master §69–77, §70 Content Object).

## Escopo

- Content Object persistido em SQLite (`content` + `content_versions`, migration V3).
- Scoring determinístico e explicável (componentes + breakdown + confiança honesta).
- Pipeline de status com transições validadas (nunca um salto ilegal silencioso).
- Repurposing determinístico (adapta; nunca copia mecanicamente; marcado mock).
- CLI `geos content` + handlers de workflow (`content.ideate`, `content.draft`
  persistente) para fechar o vertical slice.

## Fora de escopo (fases seguintes)

- SEO engine, blog publisher (CMS adapters), social scheduler — SPEC-023/024/025.
- Geração de texto por ModelProvider (drafts são templates `mock: True`).

## Content Object

`content`: id, workspace_id, content_type, status, title, slug (único), topic,
audience, persona, funnel_stage, objective, keywords[], brief, sources[], body,
assets[], cta, distribution, metrics, score, score_breakdown, mock, source_workflow,
created_at, updated_at, version.

`content_versions`: snapshot do objeto a cada draft (auditabilidade).

Content types: blog_post, guide, tutorial, case_study, comparison, social_post,
carousel, thread, newsletter, video_script, short_video_script, academy_lesson,
landing_page, changelog, announcement, release_notes, faq, glossary.

## Pipeline (status)

```
IDEA → BRIEFED → DRAFTED → REVIEWING → APPROVED → SCHEDULED → PUBLISHED → ARCHIVED
        ↘ ARCHIVED (qualquer estado pode arquivar)
```

Transições inválidas levantam `ContentError` (fail loud).

## Scoring (determinístico)

Componentes 0..1: audience_fit, strategic_fit, search_potential, educational_value,
product_relevance, novelty (decai com duplicatas de tópico), distribution_potential,
effort (invertido: maior = mais barato), evergreen_potential.

- Composto = média simples; pesos configuráveis futuramente (não fixos).
- Confiança declarada em 0.5 (heurística; nunca afirma causalidade/certeza).
- Breakdown gravado para explicabilidade (SPEC §114 analogia: score + reasons).

## Requisitos-chave

- R1: todo item criado recebe score + breakdown persistidos.
- R2: slug é único (sufixo determinístico em colisão).
- R3: `produce_draft` grava snapshot em `content_versions` e bumpa version.
- R4: repurposing registra `repurposed-from:<id>` em sources e marca mock.
- R5: handlers de workflow nunca mentem — drafts retornam `mock: True`.

## Aceitação

- Testes: `tests/test_content.py` (12 testes) + ajustes em `test_workflows.py`.
- CLI: `geos content create/list/score/status/show` com transições validadas.
- Vertical slice: `content.draft` persiste via ContentEngine (research → brief →
  draft → approval → schedule continua funcionando).
