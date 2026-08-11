"""GEOS CLI (SPEC-001/007/010, mandated SPEC-101..107 bootstrap commands).

Zero-dependency beyond PyYAML; argparse-based, deterministic. Output: PT-BR.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, Settings
from .core.jobs import PermanentError, RetryPolicy, SqliteJobQueue, Worker
from .core.scheduler import Schedule, Scheduler
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
  # embeddings:
  #   provider: hash   # hash (determinístico local) | openai (chave via env GEOS_OPENAI_API_KEY)
  #   options:
  #     model: text-embedding-3-small
  #     endpoint: https://api.openai.com/v1/embeddings

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


def _embedding_provider(settings: Settings, override: str | None = None):
    """Embedding provider from config `knowledge.embeddings`, with CLI override."""
    from .intelligence.embeddings import provider_from_config

    if override:
        return provider_from_config({"embeddings": {"provider": override}})
    return provider_from_config(settings.knowledge_embeddings)


def cmd_knowledge_ingest(args: argparse.Namespace) -> int:
    from .intelligence.knowledge import ingest_directory

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = ingest_directory(
            db, root=args.path, source=args.source or Path(args.path).name,
            doc_type=args.type,
            provider=_embedding_provider(settings, args.provider),
        )
        print(f"Ingest: {result.files_seen} files | added={result.added} "
              f"updated={result.updated} unchanged={result.unchanged} "
              f"chunks={result.chunks} embeddings={result.embeddings}")
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


def cmd_knowledge_reindex(args: argparse.Namespace) -> int:
    from .intelligence.knowledge import reindex_embeddings

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        total = reindex_embeddings(db, provider=_embedding_provider(settings, args.provider))
        print(f"reindex: embeddings reconstruídos={total}")
    finally:
        db.close()
    return 0


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


def cmd_graph_extract(args: argparse.Namespace) -> int:
    """SPEC-013: rule-based entity extraction over ingested documents."""
    from .intelligence.graph import GraphService, RuleBasedExtractor
    from .storage.repos import RepoFactory

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        repo = RepoFactory(db).knowledge
        extractor = RuleBasedExtractor()
        docs = 0
        for doc in repo.list_documents():
            chunks = repo.chunks_for_document(doc["id"])
            extractor.process_document(db, doc["id"], doc["uri"], doc["title"], chunks)
            docs += 1
        stats = GraphService(db).stats()
        by_type = ", ".join(f"{k}={v}" for k, v in sorted(stats["by_type"].items()))
        print(f"graph extract: {docs} docs | nodes={stats['nodes']} edges={stats['edges']} | {by_type}")
    finally:
        db.close()
    return 0


def cmd_graph_inspect(args: argparse.Namespace) -> int:
    from .intelligence.graph import GraphService

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        graph = GraphService(db)
        stats = graph.stats()
        print(f"nodes={stats['nodes']} edges={stats['edges']}")
        for node_type, count in sorted(stats["by_type"].items()):
            print(f"  {node_type:12s} {count}")
        if args.type:
            print(f"\n{args.type} nodes:")
            for node in graph.nodes_by_type(args.type, limit=50):
                print(f"  - {node['name']} (conf={node.get('confidence')})")
    finally:
        db.close()
    return 0


def cmd_research_run(args: argparse.Namespace) -> int:
    from .domains.research import ResearchEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        engine = ResearchEngine(db)
        report = engine.run(args.question, sources_limit=args.sources_limit)
        print(f"research: {report.id} | status={report.status} | mock={report.mock} | empty={report.empty}")
        print(f"question: {report.question}")
        print(f"sources ({len(report.sources)}):")
        for source in report.sources:
            print(f"  - [{source.score:.3f}] {source.title} ({source.uri})")
        print("\nsynthesis:")
        print(f"  {report.synthesis.splitlines()[0]}")
        print("\ninsights:")
        for insight in report.insights:
            print(f"  - [{insight.get('type')}] {insight.get('content')}")
    finally:
        db.close()
    return 0


def cmd_workflows_schedule(args: argparse.Namespace) -> int:
    """SPEC-006 wiring: register a workflow's cron/interval trigger and enqueue due runs."""
    settings = _settings(args.root, args.config)
    wf_dir = _workflows_dir(settings, args.root)
    candidates = list(wf_dir.glob(f"{args.workflow_id}.yaml")) + list(
        wf_dir.glob(f"{args.workflow_id}.yml")
    )
    if not candidates:
        print(f"workflow not found: {args.workflow_id}")
        return 1
    try:
        workflow = Workflow.load(candidates[0])
    except WorkflowLoadError as exc:
        print(f"invalid workflow: {exc}")
        return 1
    trigger = workflow.trigger
    kind = str(trigger.get("kind") or trigger.get("type") or "manual")
    if kind not in ("cron", "interval"):
        print(f"workflow {workflow.id}: trigger kind={kind} não agenda (manual/event)")
        return 0
    db = _db(settings)
    db.migrate()
    try:
        schedule = Schedule.from_dict(trigger, schedule_id=workflow.id)
        queue = SqliteJobQueue(db)
        scheduler = Scheduler(queue)
        scheduler.add(schedule, kind="workflow.run", payload={"workflow_id": workflow.id})
        enqueued = scheduler.run_due()
        print(f"workflow {workflow.id}: schedule registrado ({kind}), jobs enfileirados={enqueued}")
    finally:
        db.close()
    return 0


def cmd_workflows_worker(args: argparse.Namespace) -> int:
    """Process due jobs (workflow.run) with the registered handler."""
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        queue = SqliteJobQueue(db)
        worker = Worker(queue, RetryPolicy(max_attempts=2))

        def workflow_job_handler(payload: dict[str, object], ctx: dict[str, object]) -> None:
            wf_id = str(payload.get("workflow_id", ""))
            wf_dir = _workflows_dir(settings, args.root)
            candidates = list(wf_dir.glob(f"{wf_id}.yaml")) + list(wf_dir.glob(f"{wf_id}.yml"))
            if not candidates:
                raise PermanentError(f"workflow not found: {wf_id}")
            engine = WorkflowEngine(db)
            engine.run(Workflow.load(candidates[0]),
                       inputs=dict(payload.get("inputs") or {}),
                       trace_id=ctx.get("trace_id"))

        worker.register("workflow.run", workflow_job_handler)
        if args.once:
            job = worker.run_once()
            print("worker: nenhum job pendente" if job is None else f"worker: job {job.id} executado")
        else:
            import time as _time

            count = 0
            while True:
                job = worker.run_once()
                if job is None:
                    break
                count += 1
            print(f"worker: {count} job(s) executados")
    finally:
        db.close()
    return 0


def cmd_content_list(args: argparse.Namespace) -> int:
    from .domains.content import ContentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = ContentEngine(db).list(status=args.status, content_type=args.type,
                                       limit=args.limit)
        print(f"{len(items)} content item(s)")
        for item in items:
            score = f"score={item.get('score'):.2f}" if item.get("score") is not None else "score=-   "
            print(f"  {item['status']:10s} {item['content_type']:18s} {score} "
                  f"{item['title']} ({item['slug']})")
    finally:
        db.close()
    return 0


def cmd_content_create(args: argparse.Namespace) -> int:
    from .domains.content import ContentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        engine = ContentEngine(db)
        item = engine.create_idea(args.topic, content_type=args.type,
                                  keywords=args.keywords or [],
                                  source_workflow=args.workflow)
        print(f"created {item['id']} | {item['status']} | score={item['score']}")
        print(f"  title: {item['title']} ({item['slug']})")
    finally:
        db.close()
    return 0


def cmd_content_score(args: argparse.Namespace) -> int:
    from .domains.content import ContentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = ContentEngine(db).score(args.content_id)
        print(f"score={result['score']} confidence={result['confidence']}")
        for name, value in sorted(result["breakdown"].items()):
            print(f"  {name:24s} {value:.2f}")
    finally:
        db.close()
    return 0


def cmd_content_status(args: argparse.Namespace) -> int:
    from .domains.content import ContentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = ContentEngine(db).transition(args.content_id, args.status)
        print(f"{item['id']}: {item['status']} (version={item['version']})")
    finally:
        db.close()
    return 0


def cmd_content_show(args: argparse.Namespace) -> int:
    from .domains.content import ContentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = ContentEngine(db).get(args.content_id)
        print(f"{item['title']} ({item['slug']})")
        print(f"type={item['content_type']} status={item['status']} "
              f"version={item['version']} mock={item['mock']}")
        print(f"topic: {item.get('topic')}")
        print(f"keywords: {', '.join(item.get('keywords') or []) or '-'}")
        if item.get("score") is not None:
            print(f"score: {item['score']}")
        if item.get("brief"):
            print(f"\n--- brief ---\n{item['brief']}")
        if item.get("body"):
            print(f"\n--- body ---\n{item['body']}")
    finally:
        db.close()
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
    p_ingest.add_argument("--provider", choices=["hash", "openai"], default=None,
                          help="embedding provider override (default: config or hash)")
    p_ingest.set_defaults(func=cmd_knowledge_ingest)
    p_reindex = p_knowledge_sub.add_parser("reindex", help="reconstruir embeddings de todos os docs")
    p_reindex.add_argument("--provider", choices=["hash", "openai"], default=None,
                           help="embedding provider override (default: config or hash)")
    p_reindex.set_defaults(func=cmd_knowledge_reindex)
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
    p_sched = p_workflows_sub.add_parser("schedule", help="registrar trigger cron/interval e enfileirar")
    p_sched.add_argument("workflow_id")
    p_sched.set_defaults(func=cmd_workflows_schedule)
    p_wrk = p_workflows_sub.add_parser("worker", help="processar jobs pendentes (workflow.run)")
    p_wrk.add_argument("--once", action="store_true", help="processa apenas um job")
    p_wrk.set_defaults(func=cmd_workflows_worker)

    p_graph = sub.add_parser("graph", help="knowledge graph (SPEC-013)")
    p_graph_sub = p_graph.add_subparsers(dest="graph_action", required=True)
    p_graph_sub.add_parser("extract", help="extração determinística sobre documentos ingeridos").set_defaults(
        func=cmd_graph_extract
    )
    p_inspect = p_graph_sub.add_parser("inspect", help="estatísticas e nós")
    p_inspect.add_argument("--type", default=None, help="filtrar por tipo de nó")
    p_inspect.set_defaults(func=cmd_graph_inspect)

    p_research = sub.add_parser("research", help="research engine (SPEC-021)")
    p_research_sub = p_research.add_subparsers(dest="research_action", required=True)
    p_rrun = p_research_sub.add_parser("run", help="executar research sobre a base local")
    p_rrun.add_argument("question")
    p_rrun.add_argument("--sources-limit", type=int, default=5)
    p_rrun.set_defaults(func=cmd_research_run)

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

    p_content = sub.add_parser("content", help="content engine (SPEC-022)")
    p_content_sub = p_content.add_subparsers(dest="content_action", required=True)
    p_clist = p_content_sub.add_parser("list", help="list content items")
    p_clist.add_argument("--status", default=None)
    p_clist.add_argument("--type", default=None)
    p_clist.add_argument("--limit", type=int, default=50)
    p_clist.set_defaults(func=cmd_content_list)
    p_ccreate = p_content_sub.add_parser("create", help="create a scored content idea")
    p_ccreate.add_argument("topic")
    p_ccreate.add_argument("--type", default="blog_post", help="content type")
    p_ccreate.add_argument("--keywords", action="append", default=None)
    p_ccreate.add_argument("--workflow", default=None)
    p_ccreate.set_defaults(func=cmd_content_create)
    p_cscore = p_content_sub.add_parser("score", help="recompute deterministic score")
    p_cscore.add_argument("content_id")
    p_cscore.set_defaults(func=cmd_content_score)
    p_cstatus = p_content_sub.add_parser("status", help="transition status (validated flow)")
    p_cstatus.add_argument("content_id")
    p_cstatus.add_argument("status", help="BRIEFED|DRAFTED|REVIEWING|APPROVED|SCHEDULED|PUBLISHED|ARCHIVED")
    p_cstatus.set_defaults(func=cmd_content_status)
    p_cshow = p_content_sub.add_parser("show", help="show a content item")
    p_cshow.add_argument("content_id")
    p_cshow.set_defaults(func=cmd_content_show)

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
