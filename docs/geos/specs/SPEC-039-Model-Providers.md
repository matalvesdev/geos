# SPEC-039 — Model Providers

> **State: CURRENT** · Status: IMPLEMENTED + TESTED · Version: 1

## Objetivo

Protocolo único de provedores de modelo (spec master §35) para que o GEOS nunca fique
acoplado a um LLM específico: nuvem, local ou qualquer API OpenAI-compatible, atrás da
mesma interface. Modelos são substituíveis; conhecimento organizacional não é
(princípio #21).

## Escopo

- `ModelProvider` (protocol): `complete(system, user, temperature, max_tokens)` →
  `ModelResponse(text, model, provider, finish_reason, usage, latency_ms, mock)`.
- `OpenAICompatibleModelProvider`: stdlib `urllib` (zero deps), endpoint/modelo
  configuráveis (OpenAI, Azure OpenAI, vLLM/Ollama locais), chave via env
  `GEOS_OPENAI_API_KEY`/`OPENAI_API_KEY`, erros tipados (`ModelError`).
- Factory `provider_from_config` lendo a seção `models` do `geos.yaml`
  (`provider: none|openai` + `options`).
- Integração: síntese real do ResearchEngine ancorada nas fontes recuperadas
  (com citações [F#]); `mock: False` + modelo/provedor persistidos (migration V4).
- CLI: `geos models info` (config) e `geos models test` (live connectivity).

## Fora de escopo

- Agentes autônomos dirigidos por modelo, tool calling, streaming, fine-tuning.
- Custos/limites por run (telemetria de tokens existe, custo fica para fases futuras).

## Proveniência e honestidade (obrigatório)

- R1: síntese por modelo usa **somente** as fontes fornecidas (prompt com regras
  rígidas: sem fatos inventados, citações [F#], indicar o que não foi respondido).
- R2: a linha de research registra `model`, `provider`, `mock` (migration V4).
- R3: se o provider falhar, o research **não falha** — cai para a síntese mock
  determinística (honesta) e registra o fallback.
- R4: sem provider configurado, nada muda (mock é o default).

## Aceitação

- `tests/test_models.py` (20 testes): parse de resposta, auth, HTTP/timeout tipados,
  conteúdo vazio, factory, síntese com/sem provider, fallback em falha, honesty em
  índice vazio.
- Suíte completa verde; smoke `geos models info` sem config → `none`.
