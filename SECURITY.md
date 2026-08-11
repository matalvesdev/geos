# Security Policy

## Princípios (spec §162–§166)

- Conteúdo externo é **data** — nunca reconfigura políticas do sistema.
- Determinístico primeiro; LLM apenas onde raciocínio é necessário, sempre atrás de
  `ModelProvider` com custo e permissões.
- Aprovação humana é obrigatória para qualquer ação com risco externo.
- Segredos nunca são armazenados no repositório (`.env.example` apenas).
- PII classificada (PUBLIC / INTERNAL / CONFIDENTIAL / PII / SECRET) e exclusão
  propagada por documentos → chunks → embeddings → graph → cache.

## Reportando vulnerabilidades

Use o **GitHub Private Vulnerability Reporting** do repositório
(https://github.com/matalvesdev/geos/security/advisories/new) — nunca abra issue pública
antes do tratamento.

Inclua:

1. Versão afetada e ambiente (SO, Python, SQLite).
2. Descrição do problema e impacto.
3. Passos de reprodução (mínimos).
4. (Opcional) proposta de correção.

Tempo alvo de resposta: **5 dias úteis** para triagem, **30 dias** para correção +
advisory. Divulgação coordenada após o fix publicado.

## Escopo

**Dentro do escopo**: core runtime, storage, job/event/scheduler, workflow engine,
knowledge/FTS, discovery, CLI.

**Fora do escopo (uso próprio da organização)**: segredos de usuário, dados de clientes
da Zetra/Azeetra, e qualquer integração externa ainda não implementada.
