"""GEOS CLI (SPEC-001/007/010, mandated SPEC-101..107 bootstrap commands).

Zero-dependency beyond PyYAML; argparse-based, deterministic. Output: PT-BR.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, Settings
from .update import cmd_update, get_current_version, check_for_updates
from .menu import cmd_menu
from .formatting import (
    heading, subheading, value, label, key, dim, bold, success, error, warning, info,
    status_ok, status_warn, status_error, status_info, status_arrow,
    badge_ok, badge_warn, badge_error, badge_info, badge_version, badge_spec,
    print_ok, print_warn, print_error, print_info, print_arrow, print_kv,
    print_section, print_banner, table_row, table_header, table_divider,
    Icon, Color
)
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
        from .discovery.init_defaults import default_config_yaml

        config_path.write_text(
            default_config_yaml(mode.mode), encoding="utf-8"
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

    from .formatting import (heading, status_ok, status_info, badge_ok,
                             badge_version, value, bold, dim, print_kv)

    print(heading(f"GEOS Initialization {badge_version('v' + __version__)}", level=1))
    print()
    print_kv("Mode", bold(mode.mode))
    print_kv("Confidence", value(mode.confidence))
    print_kv("Detected by", dim(mode.detected_by))
    print()
    print(f"  {bold('Evidence:')}")
    for item in mode.evidence:
        print(f"    {status_ok()} {item}")
    print()
    print(f"  {bold('Detected capabilities:')}")
    for d in detections:
        print(f"    {status_ok()} {d.name} {dim(f'({d.confidence})')} — {d.capability}")
    print()
    print_kv("Manifest", str(manifest_path.relative_to(root)))
    if registry.list():
        print(f"\n  {bold('Repositories:')}")
        for r in registry.list():
            print(f"    {status_info()} {r.id} → {r.path}")
    print(f"\n  {bold('Next:')} geos db migrate && geos doctor")
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


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """SPEC-103: scaffold a working greenfield workspace (idempotent)."""
    from .discovery.bootstrap import bootstrap_workspace

    try:
        result = bootstrap_workspace(Path(args.root).resolve(), args.config)
    except Exception as exc:  # noqa: BLE001 - bootstrap must report cleanly
        print(f"bootstrap error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(heading(f"GEOS Bootstrap {badge_version('v' + __version__)} {badge_spec('SPEC-103')}", level=1))
    print()
    print_kv("Workspace", value(result['root']))
    print_kv("Config", result['config'])
    print_kv("Workflows", str(result['workflows']))
    print_kv("Docs de exemplo", str(result['example_docs']))
    print_kv("Schema", value(f"v{result['schema_version']}"))
    print_kv("Knowledge ingest", str(result['ingested']))
    print_kv("Conteúdo seed", f"{result['content_id']} {success('APPROVED')}")
    print_kv("Automações", ', '.join(result['automations']))
    print_kv("Manifest", result['manifest'])
    print(f"\n  {bold('Próximos passos:')}")
    print(f"    {status_arrow('geos workflows list')}")
    print(f"    {status_arrow('geos knowledge search \"cash application\"')}")
    print(f"    {status_arrow('geos content list')}")
    print(f"    {status_arrow('geos analytics collect')}")
    print(f"    {status_arrow('geos doctor')}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .formatting import (status_ok, status_error, badge_ok, badge_error,
                             heading, value, bold, success, error)

    root = Path(args.root).resolve()
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        if not passed:
            ok = False
        icon = status_ok() if passed else status_error()
        detail_str = f" — {value(detail)}" if detail else ""
        print(f"  {icon} {label}{detail_str}")

    print(heading(f"GEOS Doctor", level=2))
    print()
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
    print()
    if ok:
        print(f"  {badge_ok('ALL CHECKS PASSED')}")
    else:
        print(f"  {badge_error('ISSUES FOUND')}")
    return 0 if ok else 1


def cmd_db_migrate(args: argparse.Namespace) -> int:
    settings = _settings(args.root, args.config)
    db = _db(settings)
    try:
        before = db.current_version()
        after = db.migrate()
        print(f"  {status_ok()} Schema: {value(before)} → {value(after)}")
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
        print(f"  {status_ok()} Ingest complete:")
        print(f"    files={value(result.files_seen)} added={value(result.added)} "
              f"updated={value(result.updated)} unchanged={value(result.unchanged)}")
        print(f"    chunks={value(result.chunks)} embeddings={value(result.embeddings)}")
        for err in result.errors[:10]:
            print(f"    {status_warn()} {err}")
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
        print(f"  {status_info()} {value(len(hits))} result(s) for: {bold(args.query)!r}")
        for hit in hits:
            rank_str = value(f"{hit['rank']:.1f}")
            uri_str = dim(f"({hit['uri']})")
            print(f"\n  [{rank_str}] {bold(hit['title'])} {uri_str}")
            if hit["heading"]:
                print(f"    {label('heading')}: {hit['heading']}")
            print(f"    {dim(hit['snippet'][:120])}")
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
        print(f"  {status_ok()} Reindex: embeddings reconstruídos={value(total)}")
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
        print(f"  {status_ok()} Workflow: {bold(result.workflow_id)}")
        print(f"    {label('status')}: {success(result.status.value)} {label('trace')}: {dim(result.trace_id)}")
        for step in result.steps:
            step_status = success(step.status.value) if step.status.value == 'SUCCESS' else error(step.status.value) if step.status.value == 'FAILED' else warning(step.status.value)
            extra = f" {error(step.error)}" if step.error else ""
            print(f"    {status_arrow()} {step.id:24s} {step_status}{extra}")
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
        print(f"  {status_info()} {value(len(runs))} run(s)")
        for run in runs:
            status_color = success(run.status) if run.status == 'SUCCESS' else error(run.status) if run.status == 'FAILED' else warning(run.status)
            print(f"    {dim(run.started_at[:19])} {(run.workflow_id or run.agent or '-'):24s} "
                  f"{status_color:8s} {dim(run.error or '')}")
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
        print(f"  {status_warn()} {value(len(pending))} pending approval(s)")
        for approval in pending:
            print(f"    {dim(approval.id[:12])} {bold(approval.action)} {label('risk')}={warning(approval.risk)} {label('agent')}={approval.agent}")
    finally:
        db.close()
    return 0


def cmd_approvals_decide(args: argparse.Namespace) -> int:
    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        from .core.approvals import ApprovalEngine

        approval = ApprovalEngine(db, settings.approvals).decide(
            args.approval_id, args.decision, args.by or "cli")
        print(f"{approval.id}: {approval.status} (decision={approval.decision} "
              f"by={approval.decided_by})")
        print("  automations (e.g. `geos social worker`) podem executar agora.")
    finally:
        db.close()
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """SPEC-106: deterministic integration plan from manifest + local state."""
    root = Path(args.root).resolve()
    manifest = load_manifest(root / MANIFEST_PATH)
    if manifest is None:
        print("no manifest found — run `geos init` or `geos bootstrap` first")
        return 1

    from .core.automations import AutomationRegistry

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        # Local state: what GEOS already has (knowledge, content, automations).
        from .storage.repos import RepoFactory

        repo = RepoFactory(db)
        docs = len(repo.knowledge.list_documents())
        content = len(repo.content.list())
        blog = len(repo.blog.list())
        social = len(repo.social.list())
        automations = AutomationRegistry(root / ".geos" / "automations.json").list()
        # Deterministic phased plan (ADR-0005: shadow mode first, approvals gated).
        phases: list[tuple[str, list[str]]] = [
            ("1 · Fundamentos", [
                "geos doctor  (ambiente + schema)",
                "geos db migrate  (schema v9)",
                "geos knowledge ingest docs --source docs  (base de conhecimento)",
            ]),
            ("2 · Conhecimento & Research", [
                "geos graph extract  (nós/arestas determinísticos)",
                "geos research run \"<pergunta>\"  (síntese mock ou LLM)",
            ]),
            ("3 · Conteúdo", [
                "geos content create \"<tema>\"  (ideia pontuada)",
                "geos content draft <id>  (rascunho versionado)",
                "geos content status <id> APPROVED  (revisão humana)",
            ]),
            ("4 · Distribuição (aprovação obrigatória)", [
                "geos blog prepare <id> && geos blog publish <post> --approve",
                "geos social prepare <id> --channel x|linkedin|bluesky",
                "geos social publish <post> --approve  (ou approvals decide + worker)",
            ]),
            ("5 · Crescimento & Medição", [
                "geos opportunities collect && geos opportunities score <id>",
                "geos analytics collect  (snapshot + insights)",
                "geos automations register  (rotinas agendadas)",
            ]),
        ]
        print(f"GEOS Plan — mode={manifest.get('mode')} "
              f"(confidence={manifest.get('mode_confidence')})")
        print(f"Estado local: docs={docs} content={content} blog={blog} "
              f"social={social} automações={len(automations)}")
        for title, steps in phases:
            print(f"\n{title}:")
            for step in steps:
                print(f"  → {step}")
        print("\nPrincípio: shadow mode + aprovação humana antes de qualquer")
        print("ação externa (ADR-0005); nada documentado sem estar implementado.")
        return 0
    finally:
        db.close()


def cmd_automations_register(args: argparse.Namespace) -> int:
    from .core.automations import (AutomationRegistry, register_default_automations)

    root = Path(args.root).resolve()
    registry = AutomationRegistry(root / ".geos" / "automations.json")
    added = register_default_automations(registry)
    print(f"automações registradas: {len(registry.list())} "
          f"(novas: {', '.join(added) or 'nenhuma'})")
    for entry in registry.list():
        print(f"  {entry.id:22s} cron={entry.cron:16s} kind={entry.kind}")
    return 0


def cmd_automations_list(args: argparse.Namespace) -> int:
    from .core.automations import AutomationRegistry

    root = Path(args.root).resolve()
    registry = AutomationRegistry(root / ".geos" / "automations.json")
    entries = registry.list()
    print(f"  {status_info()} {value(len(entries))} automação(ões) agendada(s)")
    for entry in entries:
        print(f"    {bold(entry.id):22s} {label('cron')}={value(entry.cron):16s} {label('kind')}={entry.kind}")
    return 0


def cmd_automations_run(args: argparse.Namespace) -> int:
    """Enqueue due schedules and process them (handlers: social.worker,
    analytics.collect, opportunities.collect, seo.audit, workflow.run)."""
    from .core.automations import AutomationRegistry, run_automations

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        registry = AutomationRegistry(Path(args.root).resolve() / ".geos"
                                      / "automations.json")
        enqueued, processed = run_automations(registry, db,
                                              approvals=settings.approvals)
        print(f"  {status_ok()} Automations: enfileirados={value(enqueued)} processados={value(processed)}")
    finally:
        db.close()
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
    from .core.models import provider_from_config

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        engine = ResearchEngine(db, model_provider=provider_from_config(settings.models))
        report = engine.run(args.question, sources_limit=args.sources_limit)
        synth_line = (report.synthesis or "").splitlines()[0]
        print(f"research: {report.id} | status={report.status} | mock={report.mock} | empty={report.empty}")
        if report.model:
            print(f"model: {report.model} (provider={report.provider})")
        print(f"question: {report.question}")
        print(f"sources ({len(report.sources)}):")
        for source in report.sources:
            print(f"  - [{source.score:.3f}] {source.title} ({source.uri})")
        print("\nsynthesis:")
        print(f"  {synth_line}")
        print("\ninsights:")
        for insight in report.insights:
            print(f"  - [{insight.get('type')}] {insight.get('content')}")
    finally:
        db.close()
    return 0


def cmd_models_info(args: argparse.Namespace) -> int:
    from .core.models import provider_from_config

    settings = _settings(args.root, args.config)
    try:
        provider = provider_from_config(settings.models)
    except Exception as exc:  # noqa: BLE001
        print(f"models: config error — {type(exc).__name__}: {exc}")
        return 1
    if provider is None:
        print("models: none (síntese determinística mock — configure `models:` no geos.yaml)")
        return 0
    meta = provider.metadata()
    print(f"models: provider={meta.get('provider')} model={meta.get('model')}")
    print(f"  endpoint: {meta.get('endpoint')}")
    return 0


def cmd_models_test(args: argparse.Namespace) -> int:
    from .core.models import provider_from_config

    settings = _settings(args.root, args.config)
    try:
        provider = provider_from_config(settings.models)
        if provider is None:
            print("models: none — nada para testar (configure `models:` no geos.yaml)")
            return 1
        response = provider.complete(
            "Você é um verificador. Responda apenas: OK.", "Teste de conectividade GEOS.",
            max_tokens=8,
        )
        print(f"models: OK — {response.model} respondeu em {response.latency_ms}ms")
        print(f"  resposta: {response.text[:120]}")
        return 0
    except Exception as exc:  # noqa: BLE001 - test must report failures cleanly
        print(f"models: FAIL — {type(exc).__name__}: {exc}")
        return 1


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


def cmd_content_draft(args: argparse.Namespace) -> int:
    from .domains.content import ContentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = ContentEngine(db).produce_draft(args.content_id)
        print(f"{item['id']}: {item['status']} (version={item['version']}, mock={item['mock']})")
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


def cmd_seo_audit(args: argparse.Namespace) -> int:
    from .domains.seo import SeoEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        scopes = tuple(args.scopes or ("docs", "content"))
        result = SeoEngine(db).run_audit(scopes=scopes)
        summary = result["summary"]
        print(f"seo audit: {result['audit_id']} | scopes={', '.join(summary['scopes'])}")
        print(f"  total={summary['total']} critical={summary.get('critical', 0)} "
              f"warning={summary.get('warning', 0)} info={summary.get('info', 0)}")
        for issue in result["issues"][: args.limit]:
            target = f" ({issue['target']})" if issue["target"] else ""
            print(f"  [{issue['severity']:8s}] {issue['category']}: {issue['title']}{target}")
        if args.verbose:
            for issue in result["issues"][: args.limit]:
                if issue.get("recommendation"):
                    print(f"      → {issue['recommendation']}")
    finally:
        db.close()
    return 0


def cmd_seo_issues(args: argparse.Namespace) -> int:
    from .domains.seo import SeoEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        issues = SeoEngine(db).list_issues(severity=args.severity)
        print(f"{len(issues)} seo issue(s) registradas")
        for issue in issues[: args.limit]:
            target = f" ({issue['target']})" if issue["target"] else ""
            print(f"  [{issue['severity']:8s}] {issue['category']}: {issue['title']}{target}")
    finally:
        db.close()
    return 0


def cmd_opportunities_collect(args: argparse.Namespace) -> int:
    from .domains.growth import OpportunityEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        created = OpportunityEngine(db).collect()
        print(f"opportunities collect: research={created['research']} "
              f"seo={created['seo']} skipped={created['skipped']}")
    finally:
        db.close()
    return 0


def cmd_opportunities_list(args: argparse.Namespace) -> int:
    from .domains.growth import OpportunityEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = OpportunityEngine(db).list(method=args.method, top=args.top,
                                           status=args.status)
        print(f"{len(items)} opportunity(ies) — scoring: {args.method}")
        for item in items:
            score = f"{item.get('score'):.3f}" if item.get("score") is not None else "-"
            print(f"  [{score:8s}] {item['id']} | {item['source']:10s} {item['status']:12s} "
                  f"{item['problem'][:60]}")
        if args.verbose:
            for item in items:
                breakdown = item.get("breakdown") or {}
                print(f"      {item['id']} breakdown={breakdown.get('formula', '')}")
                for key, value in breakdown.items():
                    if key not in ("method", "formula", "score", "reasons"):
                        print(f"        {key}: {value}")
    finally:
        db.close()
    return 0


def cmd_opportunities_create(args: argparse.Namespace) -> int:
    from .domains.growth import OpportunityEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = OpportunityEngine(db).create(
            problem=args.problem, audience=args.audience, evidence=args.evidence,
            impact=args.impact, confidence=args.confidence, effort=args.effort,
            reach=args.reach,
        )
        print(f"created {item['id']} | {item['status']}")
        print(f"  {item['problem']}")
    finally:
        db.close()
    return 0


def cmd_opportunities_score(args: argparse.Namespace) -> int:
    from .domains.growth import OpportunityEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        engine = OpportunityEngine(db)
        if any(v is not None for v in (args.impact, args.confidence, args.effort,
                                       args.reach)):
            engine.update_components(args.opportunity_id, impact=args.impact,
                                     confidence=args.confidence, effort=args.effort,
                                     reach=args.reach)
        item = engine.score(args.opportunity_id, method=args.method)
        breakdown = item.get("breakdown") or {}
        print(f"score ({args.method}) = {item['score']}")
        print(f"  formula: {breakdown.get('formula')}")
        for key, value in breakdown.items():
            if key not in ("method", "formula", "score", "reasons"):
                print(f"  {key}: {value}")
    finally:
        db.close()
    return 0


def cmd_experiments_create(args: argparse.Namespace) -> int:
    from .domains.growth import ExperimentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = ExperimentEngine(db).from_opportunity(
            args.opportunity_id, primary_metric=args.metric, change=args.change,
            hypothesis=args.hypothesis,
        )
        print(f"created {item['id']} | {item['status']} | metric={item['primary_metric']}")
        print(f"  hipótese: {item['hypothesis'][:100]}")
    finally:
        db.close()
    return 0


def cmd_experiments_list(args: argparse.Namespace) -> int:
    from .domains.growth import ExperimentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = ExperimentEngine(db).list(status=args.status)
        print(f"{len(items)} experimento(s)")
        for item in items:
            decision = item.get("decision") or ""
            print(f"  {item['status']:10s} {item['primary_metric']:30s} "
                  f"{item['hypothesis'][:50]} {decision}")
    finally:
        db.close()
    return 0


def cmd_experiments_transition(args: argparse.Namespace) -> int:
    from .domains.growth import ExperimentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = ExperimentEngine(db).transition(args.experiment_id, args.status)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_experiments_complete(args: argparse.Namespace) -> int:
    from .domains.growth import ExperimentEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = ExperimentEngine(db).complete(
            args.experiment_id, result=args.result, analysis=args.analysis or "",
            decision=args.decision, learning=args.learning,
        )
        print(f"{item['id']}: COMPLETED | decision={item['decision']}")
        print(f"  learning: {item['learning'][:120]}")
    finally:
        db.close()
    return 0


def cmd_blog_prepare(args: argparse.Namespace) -> int:
    from .domains.blog import BlogEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        # Resolve the publish dir against the workspace root (default: blog/).
        publish_dir = args.dir or "blog"
        if not Path(publish_dir).is_absolute():
            publish_dir = str(Path(args.root) / publish_dir)
        engine = BlogEngine(db, publish_dir=publish_dir, approvals=settings.approvals)
        post = engine.prepare(args.content_id, adapter=args.adapter)
        print(f"prepared {post['id']} | {post['status']} | slug={post['slug']}")
        print(f"  adapter={post['adapter']} dir={publish_dir}")
    finally:
        db.close()
    return 0


def cmd_blog_list(args: argparse.Namespace) -> int:
    from .domains.blog import BlogEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        posts = BlogEngine(db, approvals=settings.approvals).list(status=args.status)
        print(f"{len(posts)} blog post(s)")
        for post in posts:
            print(f"  {post['status']:16s} {post['id']} {post['slug']:40s} "
                  f"{post['title'][:40]}")
    finally:
        db.close()
    return 0


def cmd_blog_publish(args: argparse.Namespace) -> int:
    from .domains.blog import BlogEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        engine = BlogEngine(db, approvals=settings.approvals)
        post = engine.publish(args.post_id, approve=args.approve,
                              decided_by=args.by or "cli")
        if post["status"] == "APPROVAL_PENDING":
            print(f"{post['id']}: {post['status']} — aprovação humana obrigatória "
                  f"(blog.publish, SPEC-024 R1)")
            print(f"  approval_id={post.get('approval_id')} — reexecute com --approve após decidir")
        else:
            print(f"{post['id']}: {post['status']}")
            print(f"  path: {post.get('published_path')} url: {post.get('published_url')}")
            print(f"  approval_id={post.get('approval_id')}")
    finally:
        db.close()
    return 0


def cmd_control_center_build(args: argparse.Namespace) -> int:
    """SPEC-038: gerar dashboard HTML estático autocontido."""
    from .domains.control_center import ControlCenter

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        output = args.output or str(Path(args.root) / "control-center.html")
        path = ControlCenter(db).build(output)
        print(f"control-center: {path} gerado")
        print("  abra no navegador (HTML estático, sem servidor).")
    finally:
        db.close()
    return 0


def cmd_analytics_collect(args: argparse.Namespace) -> int:
    from .domains.analytics import AnalyticsEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = AnalyticsEngine(db).collect()
        print(f"analytics: snapshot {result['snapshot_id']} | "
              f"{result['summary']['count']} métricas | "
              f"{len(result['insights'])} insight(s)")
        for insight in result["insights"]:
            print(f"  [{insight['insight_type']:13s}] {insight['content']}")
    finally:
        db.close()
    return 0


def cmd_analytics_metrics(args: argparse.Namespace) -> int:
    from .domains.analytics import AnalyticsEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        metrics = AnalyticsEngine(db).metrics(domain=args.domain)
        print(f"{len(metrics)} métrica(s)" + (f" (domínio: {args.domain})" if args.domain else ""))
        for name, value in sorted(metrics.items()):
            print(f"  {name:28s} {value}")
    finally:
        db.close()
    return 0


def cmd_analytics_insights(args: argparse.Namespace) -> int:
    from .domains.analytics import AnalyticsEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        insights = AnalyticsEngine(db).insights(insight_type=args.type)
        print(f"{len(insights)} insight(s)" + (f" ({args.type})" if args.type else ""))
        for insight in insights[: args.limit]:
            print(f"  [{insight['insight_type']:13s}] {insight['content']}")
            if insight.get("evidence"):
                print(f"      evidência: {insight['evidence']}")
    finally:
        db.close()
    return 0


def cmd_social_prepare(args: argparse.Namespace) -> int:
    from .domains.social import SocialEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        publish_dir = args.dir or "social"
        if not Path(publish_dir).is_absolute():
            publish_dir = str(Path(args.root) / publish_dir)
        engine = SocialEngine(db, publish_dir=publish_dir, approvals=settings.approvals)
        post = engine.prepare(args.content_id, channel=args.channel,
                              adapter=args.adapter, scheduled_at=args.at)
        print(f"prepared {post['id']} | {post['status']} | "
              f"channel={post['channel']} slug={post['slug']}")
        print(f"  chars={len(post['text'])} hashtags={len(post['hashtags'])}")
        if post.get("scheduled_at"):
            print(f"  scheduled_at={post['scheduled_at']}")
    finally:
        db.close()
    return 0


def cmd_social_list(args: argparse.Namespace) -> int:
    from .domains.social import SocialEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        posts = SocialEngine(db, approvals=settings.approvals).list(
            status=args.status, channel=args.channel)
        print(f"{len(posts)} social post(s)")
        for post in posts:
            at = post.get("scheduled_at") or ""
            print(f"  {post['status']:16s} {post['channel']:10s} "
                  f"{post['id']} {post['slug'][:30]:30s} {at[:19]}")
    finally:
        db.close()
    return 0


def cmd_social_due(args: argparse.Namespace) -> int:
    from .domains.social import SocialEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        posts = SocialEngine(db, approvals=settings.approvals).due()
        print(f"{len(posts)} social post(s) agendados vencidos")
        for post in posts:
            print(f"  {post['id']} {post['channel']:10s} {post['slug'][:40]}"
                  f" scheduled_at={post.get('scheduled_at')}")
    finally:
        db.close()
    return 0


def cmd_social_worker(args: argparse.Namespace) -> int:
    """Execute pre-approved, due social posts (SPEC-025 R4, L3 APPROVED)."""
    from .domains.social import SocialEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = SocialEngine(db, approvals=settings.approvals).worker()
        print(f"social worker: publicados={result['published']} "
              f"aguardando={result['waiting']}")
        if result["waiting"]:
            print("  aguardando: aprovação humana pendente ou janela futura — "
                  "use `geos approvals list` + `approvals decide`")
    finally:
        db.close()
    return 0


def cmd_social_publish(args: argparse.Namespace) -> int:
    from .domains.social import SocialEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        engine = SocialEngine(db, approvals=settings.approvals)
        post = engine.publish(args.post_id, approve=args.approve,
                              decided_by=args.by or "cli")
        if post["status"] in ("APPROVAL_PENDING", "SCHEDULED"):
            print(f"{post['id']}: {post['status']} — "
                  f"aprovação humana obrigatória (social.publish, SPEC-025 R1)")
            print(f"  approval_id={post.get('approval_id')} — reexecute com --approve"
                  + (" após decidir" if post["status"] == "APPROVAL_PENDING" else ""))
        else:
            print(f"{post['id']}: {post['status']}")
            print(f"  path: {post.get('published_path')} url: {post.get('published_url')}")
            print(f"  approval_id={post.get('approval_id')}")
    finally:
        db.close()
    return 0


def cmd_campaigns_create(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        engine = CampaignEngine(db)
        item = engine.create(
            name=args.name,
            campaign_type=args.type,
            hypothesis=args.hypothesis,
            objective=args.objective,
            audience=args.audience,
            budget=args.budget,
            start_date=args.start_date,
            end_date=args.end_date,
            tags=args.tags,
        )
        print(f"created {item['id']} | {item['status']} | {item['campaign_type']}")
        print(f"  name: {item['name']} ({item['slug']})")
    finally:
        db.close()
    return 0


def cmd_campaigns_list(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        items = CampaignEngine(db).list(
            status=args.status, campaign_type=args.type, limit=args.limit
        )
        print(f"{len(items)} campaign(s)")
        for item in items:
            budget = f"budget={item['budget']:.0f}" if item.get("budget") else "budget=-"
            print(f"  {item['status']:10s} {item['campaign_type']:22s} {budget:14s} "
                  f"{item['name']} ({item['slug']})")
    finally:
        db.close()
    return 0


def cmd_campaigns_show(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).get(args.campaign_id)
        print(f"{item['name']} ({item['slug']})")
        print(f"type={item['campaign_type']} status={item['status']}")
        if item.get("hypothesis"):
            print(f"hypothesis: {item['hypothesis']}")
        if item.get("objective"):
            print(f"objective: {item['objective']}")
        if item.get("audience"):
            print(f"audience: {item['audience']}")
        if item.get("budget"):
            print(f"budget: {item['budget']} (spent: {item.get('total_spend', 0)})")
        if item.get("start_date"):
            print(f"period: {item['start_date']} → {item.get('end_date', '?')}")
        tags = item.get("tags") or []
        if tags:
            print(f"tags: {', '.join(tags)}")
    finally:
        db.close()
    return 0


def cmd_campaigns_activate(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).activate(args.campaign_id)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_campaigns_pause(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).pause(args.campaign_id)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_campaigns_complete(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).complete(args.campaign_id, result=args.result)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_campaigns_cancel(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).cancel(args.campaign_id, reason=args.reason)
        print(f"{item['id']}: {item['status']}")
    finally:
        db.close()
    return 0


def cmd_campaigns_add_content(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).add_content(args.campaign_id, args.content_id)
        print(f"added content {args.content_id} to campaign {item['id']}")
    finally:
        db.close()
    return 0


def cmd_campaigns_add_social(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).add_social_post(args.campaign_id, args.post_id)
        print(f"added social post {args.post_id} to campaign {item['id']}")
    finally:
        db.close()
    return 0


def cmd_campaigns_add_experiment(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        item = CampaignEngine(db).add_experiment(args.campaign_id, args.experiment_id)
        print(f"added experiment {args.experiment_id} to campaign {item['id']}")
    finally:
        db.close()
    return 0


def cmd_campaigns_record_metric(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        CampaignEngine(db).record_metric(
            args.campaign_id, args.metric_name, args.value, source=args.source
        )
        print(f"recorded {args.metric_name}={args.value} for campaign {args.campaign_id}")
    finally:
        db.close()
    return 0


def cmd_campaigns_record_spend(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        CampaignEngine(db).record_spend(
            args.campaign_id, args.amount, description=args.description
        )
        print(f"recorded spend={args.amount} for campaign {args.campaign_id}")
    finally:
        db.close()
    return 0


def cmd_campaigns_summary(args: argparse.Namespace) -> int:
    from .domains.campaigns import CampaignEngine

    settings = _settings(args.root, args.config)
    db = _db(settings)
    db.migrate()
    try:
        result = CampaignEngine(db).summary(args.campaign_id)
        campaign = result["campaign"]
        print(f"Campaign: {campaign['name']} ({campaign['slug']})")
        print(f"Status: {campaign['status']} | Type: {campaign['campaign_type']}")
        print(f"Content: {result['content_count']} | Social: {result['social_posts_count']} "
              f"| Experiments: {result['experiments_count']}")
        budget = result["budget"]
        if budget["budget"]:
            print(f"Budget: {budget['budget']:.0f} | Spent: {budget['total_spend']:.0f} "
                  f"| Remaining: {budget['remaining']:.0f} ({budget['utilization']:.1f}%)")
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
    from .formatting import print_banner, bold, value, dim

    parser = argparse.ArgumentParser(
        prog="geos",
        description="GEOS — Growth, Education & Organizational System",
    )
    parser.add_argument("--version", action="version",
                        version=f"geos {bold('v' + __version__)} — {dim('AI Agent Framework for Growth')}")
    parser.add_argument("--root", default=".", help="workspace root (default: .)")
    parser.add_argument("--config", default=None, help="path to geos.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="detect mode, create .geos/, manifest, registry")
    p_init.add_argument("--mode", choices=["greenfield", "brownfield", "standalone"],
                        help="override automatic mode detection")
    p_init.set_defaults(func=cmd_init)

    sub.add_parser("doctor", help="environment + config checks").set_defaults(func=cmd_doctor)

    p_update = sub.add_parser("update", help="check for updates or install latest version")
    p_update.add_argument("--check", action="store_true", dest="check_only",
                          help="only check for updates, don't install")
    p_update.add_argument("--force", action="store_true",
                          help="force update even if already up to date")
    p_update.add_argument("--pip", action="store_true",
                          help="use pip install from PyPI instead of GitHub")
    p_update.set_defaults(func=cmd_update)

    p_menu = sub.add_parser("menu", help="show all available commands")
    p_menu.add_argument("command", nargs="?", default=None,
                        help="show help for specific command")
    p_menu.add_argument("--list", action="store_true",
                        help="flat list of all commands")
    p_menu.set_defaults(func=cmd_menu)

    p_bootstrap = sub.add_parser("bootstrap",
                                 help="SPEC-103: scaffold greenfield workspace")
    p_bootstrap.set_defaults(func=cmd_bootstrap)

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

    p_seo = sub.add_parser("seo", help="SEO engine (SPEC-023)")
    p_seo_sub = p_seo.add_subparsers(dest="seo_action", required=True)
    p_audit = p_seo_sub.add_parser("audit", help="auditoria determinística (docs + content)")
    p_audit.add_argument("--scope", action="append", dest="scopes", default=None,
                         choices=["docs", "content"])
    p_audit.add_argument("--limit", type=int, default=30)
    p_audit.add_argument("--verbose", action="store_true", help="mostra recomendações")
    p_audit.set_defaults(func=cmd_seo_audit)
    p_issues = p_seo_sub.add_parser("issues", help="listar issues persistidas")
    p_issues.add_argument("--severity", choices=["critical", "warning", "info"])
    p_issues.add_argument("--limit", type=int, default=50)
    p_issues.set_defaults(func=cmd_seo_issues)

    p_opportunities = sub.add_parser("opportunities", help="opportunity engine (SPEC-034)")
    p_opp_sub = p_opportunities.add_subparsers(dest="opportunities_action", required=True)
    p_opp_sub.add_parser("collect", help="criar oportunidades de research + SEO gaps").set_defaults(
        func=cmd_opportunities_collect
    )
    p_opp_list = p_opp_sub.add_parser("list", help="oportunidades priorizadas")
    p_opp_list.add_argument("--method", choices=["ice", "rice"], default="rice")
    p_opp_list.add_argument("--top", type=int, default=None)
    p_opp_list.add_argument("--status", default=None)
    p_opp_list.add_argument("--verbose", action="store_true")
    p_opp_list.set_defaults(func=cmd_opportunities_list)
    p_opp_create = p_opp_sub.add_parser("create", help="criar oportunidade manual")
    p_opp_create.add_argument("problem")
    p_opp_create.add_argument("--audience", default=None)
    p_opp_create.add_argument("--evidence", default=None)
    p_opp_create.add_argument("--impact", type=float, default=None)
    p_opp_create.add_argument("--confidence", type=float, default=None)
    p_opp_create.add_argument("--effort", type=float, default=None)
    p_opp_create.add_argument("--reach", type=float, default=None)
    p_opp_create.set_defaults(func=cmd_opportunities_create)
    p_opp_score = p_opp_sub.add_parser("score", help="scoring ICE/RICE explicável")
    p_opp_score.add_argument("opportunity_id")
    p_opp_score.add_argument("--method", choices=["ice", "rice"], default="ice")
    p_opp_score.add_argument("--impact", type=float, default=None)
    p_opp_score.add_argument("--confidence", type=float, default=None)
    p_opp_score.add_argument("--effort", type=float, default=None)
    p_opp_score.add_argument("--reach", type=float, default=None)
    p_opp_score.set_defaults(func=cmd_opportunities_score)

    p_experiments = sub.add_parser("experiments", help="experiment engine (SPEC-034)")
    p_exp_sub = p_experiments.add_subparsers(dest="experiments_action", required=True)
    p_exp_create = p_exp_sub.add_parser("create", help="criar experimento de uma oportunidade")
    p_exp_create.add_argument("opportunity_id")
    p_exp_create.add_argument("--metric", required=True, help="primary metric")
    p_exp_create.add_argument("--change", default=None)
    p_exp_create.add_argument("--hypothesis", default=None)
    p_exp_create.set_defaults(func=cmd_experiments_create)
    p_exp_list = p_exp_sub.add_parser("list", help="listar experimentos")
    p_exp_list.add_argument("--status", default=None)
    p_exp_list.set_defaults(func=cmd_experiments_list)
    p_exp_trans = p_exp_sub.add_parser("status", help="transicionar status (RUNNING/CANCELLED)")
    p_exp_trans.add_argument("experiment_id")
    p_exp_trans.add_argument("status", choices=["RUNNING", "CANCELLED"])
    p_exp_trans.set_defaults(func=cmd_experiments_transition)
    p_exp_complete = p_exp_sub.add_parser("complete", help="concluir com decisão e learning")
    p_exp_complete.add_argument("experiment_id")
    p_exp_complete.add_argument("--result", required=True)
    p_exp_complete.add_argument("--analysis", default=None)
    p_exp_complete.add_argument("--decision", choices=["ADOPT", "REJECT", "ITERATE"],
                                required=True)
    p_exp_complete.add_argument("--learning", required=True)
    p_exp_complete.set_defaults(func=cmd_experiments_complete)

    p_models = sub.add_parser("models", help="model providers (spec §35 / SPEC-039)")
    p_models_sub = p_models.add_subparsers(dest="models_action", required=True)
    p_models_sub.add_parser("info", help="show configured provider/model").set_defaults(
        func=cmd_models_info
    )
    p_models_sub.add_parser("test", help="live connectivity test").set_defaults(
        func=cmd_models_test
    )

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
    p_adecide = p_approvals_sub.add_parser("decide",
                                           help="decidir um approval (habilita worker)")
    p_adecide.add_argument("approval_id")
    p_adecide.add_argument("decision", choices=["approve", "reject"])
    p_adecide.add_argument("--by", default=None, help="quem decidiu (default: cli)")
    p_adecide.set_defaults(func=cmd_approvals_decide)

    p_blog = sub.add_parser("blog", help="blog publisher (SPEC-024)")
    p_blog_sub = p_blog.add_subparsers(dest="blog_action", required=True)
    p_bprepare = p_blog_sub.add_parser("prepare", help="preparar post de conteúdo aprovado")
    p_bprepare.add_argument("content_id")
    p_bprepare.add_argument("--adapter", default="local", help="adapter (default: local)")
    p_bprepare.add_argument("--dir", default=None,
                            help="publish dir (default: blog/ do workspace)")
    p_bprepare.set_defaults(func=cmd_blog_prepare)
    p_blist = p_blog_sub.add_parser("list", help="list blog posts")
    p_blist.add_argument("--status", default=None)
    p_blist.set_defaults(func=cmd_blog_list)
    p_bpublish = p_blog_sub.add_parser("publish", help="publicar (aprovação humana obrigatória)")
    p_bpublish.add_argument("post_id")
    p_bpublish.add_argument("--approve", action="store_true",
                            help="registrar decisão humana e publicar")
    p_bpublish.add_argument("--by", default=None, help="quem aprovou (default: cli)")
    p_bpublish.set_defaults(func=cmd_blog_publish)

    p_cc = sub.add_parser("control-center", help="SPEC-038: dashboard HTML estático")
    p_cc_sub = p_cc.add_subparsers(dest="control_center_action", required=True)
    p_cc_build = p_cc_sub.add_parser("build", help="gerar control-center.html")
    p_cc_build.add_argument("--output", default=None,
                            help="caminho do HTML (default: <workspace>/control-center.html)")
    p_cc_build.set_defaults(func=cmd_control_center_build)

    p_analytics = sub.add_parser("analytics", help="analytics engine (SPEC-035)")
    p_analytics_sub = p_analytics.add_subparsers(dest="analytics_action", required=True)
    p_analytics_sub.add_parser("collect", help="coletar snapshot de métricas + insights"
                               ).set_defaults(func=cmd_analytics_collect)
    p_ametrics = p_analytics_sub.add_parser("metrics", help="últimas métricas (por domínio)")
    p_ametrics.add_argument("--domain", default=None,
                            help="content|blog|social|seo|growth|research|telemetry")
    p_ametrics.set_defaults(func=cmd_analytics_metrics)
    p_ainsights = p_analytics_sub.add_parser("insights", help="insights persistidos")
    p_ainsights.add_argument("--type", default=None,
                             choices=["OBSERVATION", "HYPOTHESIS", "INVESTIGATION"])
    p_ainsights.add_argument("--limit", type=int, default=30)
    p_ainsights.set_defaults(func=cmd_analytics_insights)

    p_social = sub.add_parser("social", help="social scheduler (SPEC-025)")
    p_social_sub = p_social.add_subparsers(dest="social_action", required=True)
    p_sprepare = p_social_sub.add_parser("prepare", help="preparar post social de conteúdo aprovado")
    p_sprepare.add_argument("content_id")
    p_sprepare.add_argument("--channel", required=True,
                            choices=["x", "linkedin", "bluesky", "instagram"],
                            help="canal (default: obrigatório)")
    p_sprepare.add_argument("--adapter", default="local", help="adapter (default: local)")
    p_sprepare.add_argument("--dir", default=None,
                            help="publish dir (default: social/ do workspace)")
    p_sprepare.add_argument("--at", default=None,
                            help="agendar publicação (ISO datetime, SPEC-025 R4)")
    p_sprepare.set_defaults(func=cmd_social_prepare)
    p_slist = p_social_sub.add_parser("list", help="list social posts")
    p_slist.add_argument("--status", default=None)
    p_slist.add_argument("--channel", default=None)
    p_slist.set_defaults(func=cmd_social_list)
    p_sdue = p_social_sub.add_parser("due", help="list agendados vencidos (scheduler)")
    p_sdue.set_defaults(func=cmd_social_due)
    p_spublish = p_social_sub.add_parser("publish", help="publicar (aprovação humana obrigatória)")
    p_spublish.add_argument("post_id")
    p_spublish.add_argument("--approve", action="store_true",
                            help="registrar decisão humana e publicar")
    p_spublish.add_argument("--by", default=None, help="quem aprovou (default: cli)")
    p_spublish.set_defaults(func=cmd_social_publish)
    p_sworker = p_social_sub.add_parser("worker",
                                        help="executar posts pré-aprovados vencidos (L3)")
    p_sworker.set_defaults(func=cmd_social_worker)

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
    p_cdraft = p_content_sub.add_parser("draft", help="produzir rascunho (gera body, mock)")
    p_cdraft.add_argument("content_id")
    p_cdraft.set_defaults(func=cmd_content_draft)
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

    sub.add_parser("plan", help="SPEC-106: plano de integração determinístico").set_defaults(
        func=cmd_plan
    )

    p_automations = sub.add_parser("automations", help="rotinas agendadas (SPEC-006)")
    p_auto_sub = p_automations.add_subparsers(dest="automations_action", required=True)
    p_auto_sub.add_parser("register", help="registrar automações padrão").set_defaults(
        func=cmd_automations_register
    )
    p_auto_sub.add_parser("list", help="listar automações registradas").set_defaults(
        func=cmd_automations_list
    )
    p_auto_sub.add_parser("run", help="enfileirar vencidas e processar (worker)").set_defaults(
        func=cmd_automations_run
    )

    p_campaigns = sub.add_parser("campaigns", help="campaign orchestration (SPEC-040)")
    p_camp_sub = p_campaigns.add_subparsers(dest="campaigns_action", required=True)
    p_ccreate = p_camp_sub.add_parser("create", help="criar campanha")
    p_ccreate.add_argument("name")
    p_ccreate.add_argument("--type", default="content_distribution",
                           choices=["content_distribution", "lead_generation",
                                    "brand_awareness", "product_launch",
                                    "community_building", "education",
                                    "retention", "event"])
    p_ccreate.add_argument("--hypothesis", default=None)
    p_ccreate.add_argument("--objective", default=None)
    p_ccreate.add_argument("--audience", default=None)
    p_ccreate.add_argument("--budget", type=float, default=None)
    p_ccreate.add_argument("--start-date", default=None)
    p_ccreate.add_argument("--end-date", default=None)
    p_ccreate.add_argument("--tag", action="append", dest="tags", default=None)
    p_ccreate.set_defaults(func=cmd_campaigns_create)
    p_cclist = p_camp_sub.add_parser("list", help="listar campanhas")
    p_cclist.add_argument("--status", default=None)
    p_cclist.add_argument("--type", default=None)
    p_cclist.add_argument("--limit", type=int, default=50)
    p_cclist.set_defaults(func=cmd_campaigns_list)
    p_ccshow = p_camp_sub.add_parser("show", help="mostrar detalhes da campanha")
    p_ccshow.add_argument("campaign_id")
    p_ccshow.set_defaults(func=cmd_campaigns_show)
    p_ccactivate = p_camp_sub.add_parser("activate", help="ativar campanha PLANNED")
    p_ccactivate.add_argument("campaign_id")
    p_ccactivate.set_defaults(func=cmd_campaigns_activate)
    p_ccpause = p_camp_sub.add_parser("pause", help="pausar campanha ACTIVE")
    p_ccpause.add_argument("campaign_id")
    p_ccpause.set_defaults(func=cmd_campaigns_pause)
    p_cccomplete = p_camp_sub.add_parser("complete", help="concluir campanha")
    p_cccomplete.add_argument("campaign_id")
    p_cccomplete.add_argument("--result", default=None)
    p_cccomplete.set_defaults(func=cmd_campaigns_complete)
    p_cccancel = p_camp_sub.add_parser("cancel", help="cancelar campanha")
    p_cccancel.add_argument("campaign_id")
    p_cccancel.add_argument("--reason", default=None)
    p_cccancel.set_defaults(func=cmd_campaigns_cancel)
    p_ccaddcontent = p_camp_sub.add_parser("add-content", help="adicionar conteúdo à campanha")
    p_ccaddcontent.add_argument("campaign_id")
    p_ccaddcontent.add_argument("content_id")
    p_ccaddcontent.set_defaults(func=cmd_campaigns_add_content)
    p_ccaddsocial = p_camp_sub.add_parser("add-social", help="adicionar post social à campanha")
    p_ccaddsocial.add_argument("campaign_id")
    p_ccaddsocial.add_argument("post_id")
    p_ccaddsocial.set_defaults(func=cmd_campaigns_add_social)
    p_ccaddexp = p_camp_sub.add_parser("add-experiment", help="adicionar experimento à campanha")
    p_ccaddexp.add_argument("campaign_id")
    p_ccaddexp.add_argument("experiment_id")
    p_ccaddexp.set_defaults(func=cmd_campaigns_add_experiment)
    p_ccmetric = p_camp_sub.add_parser("record-metric", help="registrar métrica da campanha")
    p_ccmetric.add_argument("campaign_id")
    p_ccmetric.add_argument("metric_name")
    p_ccmetric.add_argument("value", type=float)
    p_ccmetric.add_argument("--source", default=None)
    p_ccmetric.set_defaults(func=cmd_campaigns_record_metric)
    p_ccspend = p_camp_sub.add_parser("record-spend", help="registrar gasto da campanha")
    p_ccspend.add_argument("campaign_id")
    p_ccspend.add_argument("amount", type=float)
    p_ccspend.add_argument("--description", default=None)
    p_ccspend.set_defaults(func=cmd_campaigns_record_spend)
    p_ccsummary = p_camp_sub.add_parser("summary", help="resumo completo da campanha")
    p_ccsummary.add_argument("campaign_id")
    p_ccsummary.set_defaults(func=cmd_campaigns_summary)
    # Phase 3: Leads, CRM, Meetings, Email
    from .cli_phase3 import register_phase3_parsers, register_phase4_parsers, register_phase5_parsers
    register_phase3_parsers(sub)
    register_phase4_parsers(sub)
    register_phase5_parsers(sub)


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
