"""GEOS CLI (SPEC-001/007/010, mandated SPEC-101..107 bootstrap commands).

Zero-dependency beyond PyYAML; argparse-based, deterministic. Output: PT-BR.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, Settings
from .core.workflows import Workflow, WorkflowEngine, WorkflowLoadError
from .discovery.capabilities import Detection, capability_actions, scan_capabilities
from .discovery.manifest import RepoEntry, RepositoryRegistry, build_manifest, load_manifest, write_manifest
from .discovery.mode import discover_mode
from .storage.database import Database
from .util import now_iso

DEFAULT_CONFIG = ".geos/geos.yaml"
DEFAULT_DB = ".geos/geos.db"
MANIFEST_PATH = ".geos/project-manifest.json"
REGISTRY_PATH = ".geos/repositories.json"


def _settings(root: str, config: str | None) -> Settings:
    path = config or str(Path(root) / DEFAULT_CONFIG)
    return Settings.from_path(path, root=root)


def _db(settings: Settings) -> Database:
    db = Database(settings.db_path)
    db.open()
    return db


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    mode = discover_mode(root)
    if args.mode:
        mode.mode = args.mode.upper()
        mode.confidence = "HIGH"
        mode.detected_by = "explicit"

    dot_geos = root / ".geos"
    dot_geos.mkdir(parents=True, exist_ok=True)

    config_path = root / DEFAULT_CONFIG
    if not config_path.is_file():
        config_path.write_text(
            _default_config_yaml(mode.mode), encoding="utf-8"
        )

    registry = RepositoryRegistry(root / REGISTRY_PATH)
    if mode.mode == "BROWNFIELD":
        _seed_repositories(root, registry)

    detections = scan_capabilities(root)
    for repo in registry.list():
        repo_root = Path(repo.path)
        if repo_root.is_dir():
            for detection in scan_capabilities(repo_root):
                detections.append(
                    Detection(
                        name=f"{repo.id}:{detection.name}",
                        capability=detection.capability,
                        confidence=detection.confidence,
                        evidence=detection.evidence,
                    )
                )
    manifest = build_manifest(root, mode, detections, registry.list())
    manifest_path = write_manifest(manifest, root / MANIFEST_PATH)

    docs_readme = root / "docs" / "geos" / "README.md"
    if not docs_readme.is_file():
        docs_readme.parent.mkdir(parents=True, exist_ok=True)
        docs_readme.write_text(
            "# GEOS\n\n> Inicializado por `geos init` — consulte `docs/geos/` para a árvore completa.\n",
            encoding="utf-8",
        )

    print(f"GEOS Initialization v{__version__}")
    print(f"\nMode: {mode.mode}")
    print(f"Confidence: {mode.confidence}")
    print(f"Detected by: {mode.detected_by}")
    print("\nEvidence:")
    for item in mode.evidence:
        print(f"  ✓ {item}")
    print("\nDetected capabilities:")
    for d in detections:
        print(f"  ✓ {d.name} ({d.confidence}) — {d.capability}")
    print(f"\nManifest: {manifest_path.relative_to(root)}")
    if registry.list():
        print("Repositories:")
        for r in registry.list():
            print(f"  • {r.id} -> {r.path}")
    print("\nNext: geos db migrate && geos doctor")
    return 0


def _seed_repositories(root: Path, registry: RepositoryRegistry) -> None:
    candidates = [
        ("zetra-one", "PRODUCT", ["services/api", "services/web"]),
    ]
    for repo_id, repo_type, domains in candidates:
        path = root / repo_id
        if path.is_dir() and registry.get(repo_id) is None:
            registry.add(
                RepoEntry(id=repo_id, name=repo_id, path=str(path), repo_type=repo_type,
                          domains=domains, last_indexed_at=now_iso())
            )


def _default_config_yaml(mode: str) -> str:
    repositories = ""
    if mode == "BROWNFIELD":
        repositories = (
            "\nrepositories:\n"
            "  - id: zetra-one\n"
            "    path: ./zetra-one\n"
            "    type: PRODUCT\n"
        )
    return f"""# GEOS configuration (criado por `geos init`).
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


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        status = "OK " if passed else "FAIL"
        if not passed:
            ok = False
        print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))

    check("Python >= 3.11", sys.version_info >= (3, 11), f"{sys.version_info.major}.{sys.version_info.minor}")
    try:
        import yaml  # noqa: F401

        check("PyYAML", True)
    except ImportError:
        check("PyYAML", False, "pip install PyYAML")
    import sqlite3

    check("SQLite >= 3.35 (FTS5)", sqlite3.sqlite_version_info >= (3, 35),
          sqlite3.sqlite_version)
    try:
        settings = _settings(str(root), args.config)
        check("Config", True, f"{args.config or DEFAULT_CONFIG}")
    except ConfigError as exc:
        check("Config", False, str(exc))
        settings = Settings.defaults(str(root))
    try:
        db = _db(settings)
        try:
            version = db.migrate()
            check("Database", True, f"{db.path or ':memory:'} at schema v{version}")
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        check("Database", False, str(exc))
    writable = root.is_dir()
    check("Workspace writable", writable)
    print("\nGEOS Doctor:", "ALL CHECKS PASSED" if ok else "ISSUES FOUND")
    return 0 if ok else 1


def cmd_db_migrate(args: argparse.Namespace) -> int:
    settings = _settings(args.root, args.config)
    db = _db(settings)
    try:
        before = db.current_version()
        after = db.migrate()
        print(f"Schema version: {before} -> {after}")
    finally:
        db.close()
    return 0


def cmd_knowledge_ingest(args: argparse.Namespace) -> int:
    from .intelligence.knowledge import ingest_directory

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = ingest_directory(
            db, root=args.path, source=args.source or Path(args.path).name,
            doc_type=args.type,
        )
        print(f"Ingest: {result.files_seen} files | added={result.added} "
              f"updated={result.updated} unchanged={result.unchanged} chunks={result.chunks}")
        for error in result.errors[:10]:
            print(f"  ! {error}")
    finally:
        db.close()
    return 0


def cmd_knowledge_search(args: argparse.Namespace) -> int:
    from .intelligence.knowledge import search

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        hits = search(db, query=args.query, limit=args.limit, doc_type=args.type)
        print(f"{len(hits)} result(s) for: {args.query!r}")
        for hit in hits:
            print(f"\n[{hit['rank']:.1f}] {hit['title']} ({hit['uri']})")
            if hit["heading"]:
                print(f"    heading: {hit['heading']}")
            print(f"    {hit['snippet']}")
    finally:
        db.close()
    return 0


def _workflows_dir(settings: Settings, root: str) -> Path:
    """Resolve the workflows dir: absolute → root-relative → package-relative fallback
    (so the standalone repo and the sidecar install both find the shipped examples).
    """
    wf_dir = Path(settings.workflows_dir)
    if wf_dir.is_absolute():
        return wf_dir
    root_candidate = Path(root) / wf_dir
    if root_candidate.is_dir():
        return root_candidate
    pkg_root = Path(__file__).resolve().parents[1]  # the geos repo root
    return pkg_root / wf_dir


def cmd_workflows_list(args: argparse.Namespace) -> int:
    settings = _settings(args.root, args.config)
    wf_dir = _workflows_dir(settings, args.root)
    if not wf_dir.is_dir():
        print(f"workflows dir not found: {wf_dir}")
        return 1
    workflows = sorted(wf_dir.glob("*.yaml")) + sorted(wf_dir.glob("*.yml"))
    for path in workflows:
        try:
            wf = Workflow.load(path)
            triggers = ", ".join(f"{k}={v}" for k, v in wf.trigger.items())
            print(f"{wf.id:30s} steps={len(wf.steps)} trigger={triggers}")
        except WorkflowLoadError as exc:
            print(f"{path.name:30s} INVALID: {exc}")
    return 0


def cmd_workflows_run(args: argparse.Namespace) -> int:
    settings = _settings(args.root, args.config)
    wf_dir = _workflows_dir(settings, args.root)
    candidates = list(wf_dir.glob(f"{args.workflow_id}.yaml")) + list(
        wf_dir.glob(f"{args.workflow_id}.yml")
    )
    if not candidates:
        print(f"workflow not found: {args.workflow_id} (in {wf_dir})")
        return 1
    try:
        workflow = Workflow.load(candidates[0])
    except WorkflowLoadError as exc:
        print(f"invalid workflow: {exc}")
        return 1
    inputs = {"date": now_iso()[:10], "approvals": {}}
    for item in args.approve or []:
        inputs["approvals"][item] = True
    for item in args.input or []:
        if "=" in item:
            key, value = item.split("=", 1)
            inputs[key] = value

    db = _db(settings)
    db.migrate()
    try:
        engine = WorkflowEngine(db)
        result = engine.run(workflow, inputs=inputs)
        print(f"workflow: {result.workflow_id} | status: {result.status.value} | trace: {result.trace_id}")
        for step in result.steps:
            status = step.status.value
            extra = f" | {step.error}" if step.error else ""
            print(f"  - {step.id:24s} {status}{extra}")
    finally:
        db.close()
    return 0


def cmd_runs_list(args: argparse.Namespace) -> int:
    from .core.telemetry import Telemetry

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        runs = Telemetry(db).list(status=args.status, limit=args.limit)
        print(f"{len(runs)} run(s)")
        for run in runs:
            print(f"  {run.started_at[:19]} {run.workflow_id or run.agent or '-':24s} "
                  f"{run.status:8s} {run.error or ''}")
    finally:
        db.close()
    return 0


def cmd_approvals_list(args: argparse.Namespace) -> int:
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        from .core.approvals import ApprovalEngine

        pending = ApprovalEngine(db, settings.approvals).pending()
        print(f"{len(pending)} pending approval(s)")
        for approval in pending:
            print(f"  {approval.id} {approval.action} risk={approval.risk} agent={approval.agent}")
    finally:
        db.close()
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """EXPERIMENTAL (SPEC-106): recommendation view from the last audit manifest."""
    root = Path(args.root).resolve()
    manifest = load_manifest(root / MANIFEST_PATH)
    if manifest is None:
        print("no manifest found — run `geos init` first")
        return 1
    print(f"GEOS Plan for mode={manifest.get('mode')} "
          f"(confidence={manifest.get('mode_confidence')}) [EXPERIMENTAL]")
    actions = capability_actions()
    by_action: dict[str, list[str]] = {}
    for cap in manifest.get("capabilities", []):  # type: ignore[union-attr]
        action = actions.get(cap["capability"], "INTEGRATE")
        by_action.setdefault(action, []).append(cap["name"])
    for action in ("REUSE", "INTEGRATE", "CREATE"):
        names = by_action.get(action)
        if names:
            print(f"\n{action}:")
            for name in names:
                print(f"  → {name}")
    print("\nAdopt gradually: `geos adopt <domain>` (SPEC-103/106 roadmap).")
    return 0


def cmd_repo(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    registry = RepositoryRegistry(root / REGISTRY_PATH)
    if args.action == "add":
        entry = RepoEntry(id=args.id, name=args.id, path=str(Path(args.path).resolve()),
                          repo_type=args.type, last_indexed_at=now_iso())
        registry.add(entry)
        print(f"added repository {args.id} -> {entry.path}")
    elif args.action == "list":
        for entry in registry.list():
            print(f"  {entry.id:16s} {entry.repo_type:12s} {entry.path}")
    return 0


def _force_utf8_stdio() -> None:
    """Windows cp1252 stdout breaks on ✓/→; reconfigure to UTF-8 when possible."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="geos",
        description="GEOS — Growth, Education & Organizational System",
    )
    parser.add_argument("--version", action="version", version=f"geos {__version__}")
    parser.add_argument("--root", default=".", help="workspace root (default: .)")
    parser.add_argument("--config", default=None, help="path to geos.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="detect mode, create .geos/, manifest, registry")
    p_init.add_argument("--mode", choices=["greenfield", "brownfield", "standalone"],
                        help="override automatic mode detection")
    p_init.set_defaults(func=cmd_init)

    sub.add_parser("doctor", help="environment + config checks").set_defaults(func=cmd_doctor)

    p_db = sub.add_parser("db", help="database commands")
    p_db_sub = p_db.add_subparsers(dest="db_action", required=True)
    p_db_sub.add_parser("migrate", help="apply pending migrations").set_defaults(func=cmd_db_migrate)

    p_knowledge = sub.add_parser("knowledge", help="knowledge layer")
    p_knowledge_sub = p_knowledge.add_subparsers(dest="knowledge_action", required=True)
    p_ingest = p_knowledge_sub.add_parser("ingest", help="ingest a docs directory")
    p_ingest.add_argument("path", help="directory to ingest (markdown/txt)")
    p_ingest.add_argument("--source", default=None, help="source label (default: dir name)")
    p_ingest.add_argument("--type", default="markdown", help="doc_type (default: markdown)")
    p_ingest.set_defaults(func=cmd_knowledge_ingest)
    p_search = p_knowledge_sub.add_parser("search", help="FTS search over ingested chunks")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--type", default=None)
    p_search.set_defaults(func=cmd_knowledge_search)

    p_workflows = sub.add_parser("workflows", help="workflow engine")
    p_workflows_sub = p_workflows.add_subparsers(dest="workflow_action", required=True)
    p_workflows_sub.add_parser("list", help="list workflows in workflows dir").set_defaults(
        func=cmd_workflows_list
    )
    p_run = p_workflows_sub.add_parser("run", help="run a workflow")
    p_run.add_argument("workflow_id")
    p_run.add_argument("--input", action="append", help="key=value extra input")
    p_run.add_argument("--approve", action="append", help="approve an approval-gated step")
    p_run.set_defaults(func=cmd_workflows_run)

    p_runs = sub.add_parser("runs", help="run telemetry")
    p_runs_sub = p_runs.add_subparsers(dest="runs_action", required=True)
    p_runs_list = p_runs_sub.add_parser("list", help="list recorded runs")
    p_runs_list.add_argument("--status", default=None)
    p_runs_list.add_argument("--limit", type=int, default=50)
    p_runs_list.set_defaults(func=cmd_runs_list)

    p_approvals = sub.add_parser("approvals", help="approval engine")
    p_approvals_sub = p_approvals.add_subparsers(dest="approvals_action", required=True)
    p_approvals_sub.add_parser("list", help="list pending approvals").set_defaults(
        func=cmd_approvals_list
    )

    sub.add_parser("plan", help="EXPERIMENTAL: adoption recommendations from manifest").set_defaults(
        func=cmd_plan
    )

    p_repo = sub.add_parser("repo", help="repository registry")
    p_repo_sub = p_repo.add_subparsers(dest="repo_action", required=True)
    p_repo_add = p_repo_sub.add_parser("add", help="register a repository")
    p_repo_add.add_argument("id")
    p_repo_add.add_argument("path")
    p_repo_add.add_argument("--type", default="PRODUCT")
    p_repo_add.set_defaults(func=cmd_repo, action="add")
    p_repo_list = p_repo_sub.add_parser("list", help="list repositories")
    p_repo_list.set_defaults(func=cmd_repo, action="list")

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI must not traceback on user errors
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
