# GEOS-ADR-0005 — Non-Destructive Brownfield Adoption

- **Status**: Accepted
- **Date**: 2026-08-11
- **Context**: The installation/adoption model (second spec paste) requires GEOS to work in
  GREENFIELD, BROWNFIELD and STANDALONE modes, changing the least amount of existing code, with
  reversibility, shadow mode and feature flags. Zetra One is an existing brownfield client.
- **Decision**:
  1. `geos init` performs **discovery + audit + minimal files only** (`.geos/`, `docs/geos/`).
     No product files are ever modified by GEOS bootstrap; writes to external systems require
     explicit permissions and approvals.
  2. Storage isolation: `storage.mode: isolated` (SQLite) is the brownfield default until a
     reason to share infrastructure exists.
  3. New capabilities ship **shadow-mode first** (compute, compare, never act) behind feature
     flags (`features.*` in `geos.yaml`); elevation to live requires SPEC + validation.
  4. Repository Registry (SPEC-009) is the only place GEOS learns about connected repositories;
     multi-repo and standalone control-plane operation (SPEC-108) are the same machinery.
- **Alternatives**: embedded modifications (rejected); greenfield-only assumptions (rejected).
- **Consequences**: (+): reversible, auditable, safe on Zetra One. (−): slower to first live
  automation; requires explicit approval flows before external actions.
