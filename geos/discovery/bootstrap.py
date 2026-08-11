"""Greenfield Bootstrap (SPEC-103): scaffold a working GEOS workspace.

`geos bootstrap` turns an empty directory into a runnable workspace: config +
manifest (via init), example workflows, sample docs, a migrated database with
ingested knowledge and a seeded content pipeline — then prints the next steps.
Everything is deterministic and local-first; nothing external is touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..storage.database import Database
from ..util import now_iso

# Workflows shipped in the package (copied into the workspace on bootstrap).
_WORKFLOW_FILES = (
    "hello.yaml",
    "content-factory.yaml",
    "content-idea.yaml",
    "daily-intelligence.yaml",
)

# Sample markdown docs shipped as bootstrap examples.
_EXAMPLE_DOCS = {
    "README.md": (
        "# Example workspace\n\n"
        "> Criado por `geos bootstrap` (SPEC-103). Este diretório é ingerido como "
        "conhecimento local para demonstração.\n\n"
        "## Zetra One\n\n"
        "Plataforma de growth B2B que ajuda financeiros a acelerar o cash application "
        "e a conciliação bancária. O problema é a velocidade de crédito do recebível.\n"
    ),
    "cash-application.md": (
        "# Cash application na prática\n\n"
        "O processo de dar baixa em pagamentos recebidos contra faturas em aberto. "
        "Reduz DSO e risco de fraude. Automação com matching por valor, referência e "
        "cliente reduz horas de trabalho manual.\n"
    ),
    "conciliacao-bancaria.md": (
        "# Conciliação bancária\n\n"
        "Confronto do extrato bancário com o razão contábil. Extrato sem conciliar "
        "esconde erros e atrasos. Ferramentas de automação detectam divergências "
        "antes do fechamento mensal.\n"
    ),
}

def bootstrap_workspace(root: Path, config: str | None = None) -> dict[str, Any]:
    """Scaffold a greenfield workspace. Idempotent: existing files are kept."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    # 1. Config + manifest (reuse `geos init` semantics).
    from .mode import discover_mode

    from ..config import Settings

    from .capabilities import scan_capabilities
    from .manifest import RepositoryRegistry, build_manifest, write_manifest

    mode = discover_mode(root)
    mode.mode = "GREENFIELD"
    mode.confidence = "HIGH"
    mode.detected_by = "bootstrap"
    registry = RepositoryRegistry(root / ".geos" / "repositories.json")

    config_path = Path(config) if config else root / ".geos" / "geos.yaml"
    if not config_path.is_file():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        from .init_defaults import default_config_yaml

        config_path.write_text(default_config_yaml("GREENFIELD"), encoding="utf-8")
    settings = Settings.from_path(str(config_path), root=str(root))

    # 2. Example workflows + docs.
    workflows_dir = root / "workflows"
    workflows_dir.mkdir(exist_ok=True)
    copied_workflows = _copy_workflows(workflows_dir)
    examples_dir = root / "examples" / "docs"
    examples_dir.mkdir(parents=True, exist_ok=True)
    written_docs = 0
    for name, content in _EXAMPLE_DOCS.items():
        target = examples_dir / name
        if not target.is_file():
            target.write_text(content, encoding="utf-8")
            written_docs += 1

    # 3. Database: migrate + ingest examples + seed content pipeline.
    db = Database(settings.db_path)
    db.open()
    try:
        version = db.migrate()
        ingest = _ingest_examples(db, examples_dir)
        content_id = _seed_content(db)
    finally:
        db.close()

    # 4. Persist the default automations (SPEC-006 wiring via AutomationRegistry).
    from ..core.automations import AutomationRegistry, register_default_automations

    registry = AutomationRegistry(root / ".geos" / "automations.json")
    registered = register_default_automations(registry)

    manifest_path = write_manifest(
        build_manifest(root, mode, scan_capabilities(root), registry.list()),
        root / ".geos" / "project-manifest.json",
    )

    return {
        "root": str(root),
        "config": str(config_path),
        "workflows": copied_workflows,
        "example_docs": written_docs,
        "schema_version": version,
        "ingested": ingest,
        "content_id": content_id,
        "automations": registered,
        "manifest": str(manifest_path),
        "at": now_iso(),
    }


def _copy_workflows(target: Path) -> int:
    """Copy the package-shipped example workflows into the workspace."""
    pkg_workflows = Path(__file__).resolve().parents[2] / "workflows"
    copied = 0
    if pkg_workflows.is_dir():
        for name in _WORKFLOW_FILES:
            source = pkg_workflows / name
            dest = target / name
            if source.is_file() and not dest.is_file():
                dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                copied += 1
    return copied


def _ingest_examples(db: Database, examples_dir: Path) -> dict[str, int]:
    from ..intelligence.knowledge import ingest_directory
    from ..intelligence.embeddings import provider_from_config

    result = ingest_directory(
        db, root=str(examples_dir), source="examples",
        doc_type="markdown",
        provider=provider_from_config(None),
    )
    return {
        "files_seen": result.files_seen,
        "added": result.added,
        "chunks": result.chunks,
    }


def _seed_content(db: Database) -> str:
    """Create + approve one content item so the pipeline is immediately usable.
    Idempotent: reuses an existing bootstrap-seeded item (SPEC-103)."""
    from ..storage.repos import RepoFactory

    existing = RepoFactory(db).content.list(limit=50)
    for item in existing:
        if item.get("source_workflow") == "bootstrap":
            return item["id"]

    from ..domains.content import ContentEngine

    engine = ContentEngine(db)
    item = engine.create_idea("Cash application na prática",
                              keywords=["cash application", "DSO", "automação"],
                              source_workflow="bootstrap")
    engine.write_brief(item["id"], audience="Financeiro de B2B",
                       objective="educate",
                       cta="Falar com especialista Zetra One")
    engine.produce_draft(item["id"])
    engine.transition(item["id"], "APPROVED")
    return item["id"]
