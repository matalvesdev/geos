# Exemplos

Quickstart completo (zero infraestrutura obrigatória — SQLite local apenas):

```bash
git clone https://github.com/matalvesdev/geos.git
cd geos
python -m pip install -e .        # instala o entry point `geos`
geos init --mode greenfield       # cria .geos/ (config + sqlite + manifest)
geos db migrate                   # schema v1
geos knowledge ingest examples/docs --source examples
geos knowledge search "origem de crédito"
geos workflows list               # hello, content-idea, daily-intelligence
geos workflows run hello --input message="oi geos"
geos runs list
geos doctor
```

Sem `pip install -e .`? Use `python -m geos.cli ...` no lugar de `geos`.

## Arquivos

| Arquivo | O quê |
|---|---|
| `geos.yaml` | Configuração mínima de exemplo (SPDX `storage`/`approvals`/`features`) |
| `docs/sample.md` | Documento de exemplo para ingestão + busca FTS |
| `geos/workflows/hello.yaml` | Workflow de 2 passos (echo + approval record) |
| `geos/workflows/content-idea.yaml` | Pesquisa → brief → **aprovação obrigatória** → social |
| `geos/workflows/daily-intelligence.yaml` | Scan de conhecimento diário (mock determinístico) |

O `geos init` cria `.geos/geos.yaml`, `.geos/geos.db`, `.geos/project-manifest.json` e
`docs/geos/README.md`. Nada além disso é modificado — nada de Kafka/Redis/Postgres
para o primeiro workflow.
