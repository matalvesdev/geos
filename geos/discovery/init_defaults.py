"""Default `geos.yaml` generator (SPEC-001 / SPEC-103). Shared by init + bootstrap."""

from __future__ import annotations


def default_config_yaml(mode: str = "GREENFIELD") -> str:
    repositories = ""
    if mode == "BROWNFIELD":
        repositories = (
            "\nrepositories:\n"
            "  - id: zetra-one\n"
            "    path: ./zetra-one\n"
            "    type: PRODUCT\n"
        )
    return f"""# GEOS configuration (criado por `geos init` / `geos bootstrap`).
# Estados: CURRENT / PROPOSED / PLANNED — nunca documente como existente o que não existe.

company:
  name: Example

storage:
  provider: sqlite
  mode: isolated
  path: .geos/geos.db

knowledge:
  rag: true
  graph: true
  # embeddings:
  #   provider: hash   # hash (determinístico local) | openai (chave via env GEOS_OPENAI_API_KEY)
  #   options:
  #     model: text-embedding-3-small
  #     endpoint: https://api.openai.com/v1/embeddings

# models:
#   provider: none    # none (síntese mock determinística) | openai (chave via env GEOS_OPENAI_API_KEY)
#   options:
#     model: gpt-4o-mini
#     endpoint: https://api.openai.com/v1/chat/completions

agents:
  research: true
  content: true
  seo: true
  growth: true
  leads: true
  academy: true

automations:
  daily_intelligence: false
  weekly_content: false
  weekly_growth_review: false

approvals:
  social_publish: required
  blog_publish: required
  newsletter_send: required
  meeting_invite: required

features:
  rag: true
  graph: false
  leads:
    enabled: false
    shadow_mode: true
  social_publish:
    enabled: false
  meeting_scheduler:
    enabled: false
    shadow_mode: true
{repositories}"""
