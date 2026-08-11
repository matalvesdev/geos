# Contribuindo para o GEOS

Obrigado por contribuir! O GEOS segue **Spec-Driven Development (SDD)**: nenhuma
implementação significativa começa sem especificação suficiente.

## Ciclo SDD

```
DISCOVER → AUDIT → SPECIFY → DESIGN → PLAN → IMPLEMENT → TEST → VALIDATE
→ OBSERVE → MEASURE → DOCUMENT → LEARN → IMPROVE → REPEAT
```

## Começando

```bash
git clone https://github.com/matalvesdev/geos.git
cd geos
python -m unittest discover -s tests -t .   # 83 testes, zero deps além de PyYAML
python -m geos.cli doctor
```

Dependências mínimas: Python ≥ 3.11 + PyYAML.

## Regras

1. **Spec antes de código**: features maiores começam como `docs/geos/specs/SPEC-XXX.md`
   (template no spec §191). Mudanças pequenas com teste cobrindo.
2. **Estados honestos**: nunca documente algo como existente se não está implementado
   (CURRENT / PROPOSED / PLANNED / EXPERIMENTAL / DEPRECATED / ARCHIVED).
3. **Determinístico primeiro**: datas, slugs, validação, scoring, dedup, scheduling,
   parsing → código puro. LLM só para raciocínio/síntese/escrita, atrás de `ModelProvider`.
4. **Sem god agent, sem swarms não controlados** (§41-42): cada colaboração tem
   goal/input/expected_output/budget/max_steps/timeout/exit_condition.
5. **Aprovação humana** para risco externo (publish, social, newsletter, meetings,
   paid media, destrutivas) — políticas declarativas em `geos.yaml`.
6. **Nunca commitar**: `.geos/`, `*.db`, `.env`, segredos.
7. **Changelog**: toda mudança relevante atualiza `CHANGELOG.md` (§198).

## Fluxo de PR

1. Fork + branch (`feat/`, `fix/`, `spec/`).
2. Implemente com testes (`tests/test_*.py`, `unittest`).
3. Rode a suíte: `python -m unittest discover -s tests -t .`
4. Documente (SPEC/ADR se estrutural) + entrada no CHANGELOG.
5. Abra o PR descrevendo o WHAT/WHY e evidência de testes.

## Convenções de código

- Python 3.11+, type hints em todas as assinaturas públicas.
- Dataclasses/Protocols para contratos (Pydantic é opcional, nunca obrigatório no core).
- Módulos pequenos com responsabilidade única; repositórios no lugar de SQL direto.
- Mensagens de commit claras; nenhuma alegação sem evidência.

## Código de conduta

Ao contribuir, você concorda com o [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
