"""Control Center (SPEC-038): self-contained HTML dashboard.

`geos control-center build` reads the local database (analytics snapshot,
approvals, content/blog/social pipeline, growth, telemetry, health, RAG,
runs, backups, self-audit) and renders a single self-contained HTML file —
dark theme, zero external assets, charts in pure CSS.

Phase 5 enhancements: RAG debugger, run debugger, backup management,
self-audit, and self-improvement loop.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from ..storage.database import Database
from ..storage.repos import RepoFactory
from ..util import now_iso

_CSS = """
:root{
  --bg:#0b0f17;--panel:#111827;--panel2:#0f172a;--line:#1e293b;--tx:#e2e8f0;
  --mut:#64748b;--acc:#38bdf8;--ok:#34d399;--warn:#fbbf24;--crit:#f87171;
  --pur:#a78bfa;--rad:14px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font:14px/1.55 ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;padding:28px}
header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px;margin-bottom:22px}
header h1{font-size:26px;font-weight:800;letter-spacing:-.02em}
header h1 span{color:var(--acc)}
header .meta{color:var(--mut);font-size:12.5px;text-align:right}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--line);margin:2px 4px 0 0}
.pill.ok{color:var(--ok)}.pill.warn{color:var(--warn)}.pill.crit{color:var(--crit)}
.grid{display:grid;gap:16px;margin-bottom:16px}
.grid.kpi{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.grid.two{grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--rad);padding:16px 18px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin-bottom:12px;font-weight:700}
.kpi{background:linear-gradient(160deg,var(--panel) 0%,var(--panel2) 100%);border:1px solid var(--line);border-radius:var(--rad);padding:14px 16px}
.kpi .v{font-size:24px;font-weight:800;letter-spacing:-.02em}
.kpi .l{color:var(--mut);font-size:12px;margin-top:2px}
.kpi .d{color:var(--mut);font-size:11px;margin-top:6px}
.row{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px dashed var(--line)}
.row:last-child{border-bottom:none}
.row .n{color:var(--tx)}.row .n small{color:var(--mut)}
.bar{height:8px;background:#1e293b;border-radius:99px;overflow:hidden;margin-top:4px}
.bar>i{display:block;height:100%;border-radius:99px}
.insight{border-left:3px solid var(--mut);padding:8px 12px;margin:8px 0;background:#0f172a;border-radius:0 8px 8px 0}
.insight.OBSERVATION{border-color:var(--acc)}.insight.HYPOTHESIS{border-color:var(--pur)}.insight.INVESTIGATION{border-color:var(--warn)}
.insight .t{font-weight:700;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.insight .e{color:var(--mut);font-size:12px;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--mut);text-align:left;font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;padding:6px 8px}
td{padding:7px 8px;border-top:1px solid var(--line)}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;font-weight:700}
.badge.ok{background:rgba(52,211,153,.12);color:var(--ok)}
.badge.warn{background:rgba(251,191,36,.12);color:var(--warn)}
.badge.crit{background:rgba(248,113,113,.12);color:var(--crit)}
.badge.info{background:rgba(100,116,139,.15);color:var(--tx)}
.empty{color:var(--mut);font-style:italic;font-size:13px}
footer{margin-top:26px;color:var(--mut);font-size:12px;text-align:center}
a{color:var(--acc);text-decoration:none}
@media(max-width:640px){body{padding:14px}}
"""


class ControlCenter:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- RAG debugger (Phase 5) -------------------------------------------
    def rag_debugger(self, query: str) -> dict[str, Any]:
        """Debug RAG retrieval for a query."""
        from ..intelligence.retrieval import HybridRetriever, RetrievalConfig
        
        retriever = HybridRetriever(self._db, RetrievalConfig())
        results = retriever.search(query, limit=10)
        
        return {
            "query": query,
            "results_count": len(results),
            "results": [
                {
                    "chunk_id": r.chunk_id,
                    "score": r.score,
                    "source": r.uri,
                    "title": r.title,
                    "snippet": r.snippet[:200],
                    "strategy": r.strategy,
                }
                for r in results
            ],
            "index_stats": self._rag_index_stats(),
        }

    def _rag_index_stats(self) -> dict[str, Any]:
        """Get RAG index statistics."""
        docs = self._repo.knowledge.list_documents()
        from ..storage.repos import RepoFactory
        repo = RepoFactory(self._db)
        embeddings_count = len(repo.embeddings.candidates(limit=10000))
        
        return {
            "documents": len(docs),
            "embeddings": embeddings_count,
            "doc_types": list({d.get("doc_type", "unknown") for d in docs}),
        }

    # ---- Run debugger (Phase 5) -------------------------------------------
    def run_debugger(self, run_id: str) -> dict[str, Any]:
        """Debug a specific run."""
        from ..core.telemetry import Telemetry
        telemetry = Telemetry(self._db)
        
        run = None
        for r in telemetry.list(limit=1000):
            if r.id == run_id:
                run = r
                break
        
        if run is None:
            return {"error": f"run {run_id} not found"}
        
        # Get events for this run
        events = self._repo.events.list(trace_id=run.trace_id, limit=50)
        
        return {
            "run": run.__dict__,
            "events": [
                {
                    "type": e.event_type,
                    "payload": e.payload,
                    "created_at": e.created_at,
                }
                for e in events
            ],
            "duration_ms": run.duration_ms,
            "error": run.error,
        }

    # ---- Backup management (Phase 5) --------------------------------------
    def backup_database(self, backup_path: str) -> dict[str, Any]:
        """Create a backup of the database."""
        import shutil
        from pathlib import Path
        
        src = str(self._db._path) if hasattr(self._db, "_path") else self._db.path
        if src is None:
            return {"error": "cannot backup :memory: database"}
        
        dst = Path(backup_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        
        return {
            "source": str(src),
            "destination": str(dst),
            "size_bytes": dst.stat().st_size,
            "created_at": now_iso(),
        }

    def list_backups(self, backup_dir: str = "backups") -> list[dict[str, Any]]:
        """List available backups."""
        from pathlib import Path
        
        backups_path = Path(backup_dir)
        if not backups_path.exists():
            return []
        
        backups = []
        for f in sorted(backups_path.glob("geos-*.db"), reverse=True):
            backups.append({
                "name": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
                "modified_at": f.stat().st_mtime,
            })
        return backups[:10]

    # ---- Self-audit (Phase 5) ---------------------------------------------
    def self_audit(self) -> dict[str, Any]:
        """Run self-audit checks."""
        checks = []
        
        # Schema check
        try:
            version = self._db.current_version()
            checks.append({"name": "schema", "status": "ok", "detail": f"v{version}"})
        except Exception as e:
            checks.append({"name": "schema", "status": "error", "detail": str(e)})
        
        # Knowledge check
        docs = self._repo.knowledge.list_documents()
        if docs:
            checks.append({"name": "knowledge", "status": "ok", "detail": f"{len(docs)} documents"})
        else:
            checks.append({"name": "knowledge", "status": "warning", "detail": "no documents ingested"})
        
        # Content check
        content = self._repo.content.list()
        orphaned = [c for c in content if c["status"] == "IDEA"]
        if orphaned:
            checks.append({"name": "content", "status": "warning", "detail": f"{len(orphaned)} orphaned ideas"})
        else:
            checks.append({"name": "content", "status": "ok", "detail": f"{len(content)} items"})
        
        # Approvals check
        pending = self._repo.approvals.list_pending()
        if len(pending) > 10:
            checks.append({"name": "approvals", "status": "warning", "detail": f"{len(pending)} pending (>10)"})
        else:
            checks.append({"name": "approvals", "status": "ok", "detail": f"{len(pending)} pending"})
        
        # Leads check
        leads = self._repo.leads.list()
        stale = [l for l in leads if l["status"] == "CAPTURED"]
        if len(stale) > 5:
            checks.append({"name": "leads", "status": "warning", "detail": f"{len(stale)} unqualified leads"})
        else:
            checks.append({"name": "leads", "status": "ok", "detail": f"{len(leads)} total"})
        
        # CRM check
        deals = self._repo.crm.list_deals(status="OPEN")
        stale_deals = [d for d in deals if d.get("probability", 0) < 0.2]
        if stale_deals:
            checks.append({"name": "crm", "status": "warning", "detail": f"{len(stale_deals)} low-probability deals"})
        else:
            checks.append({"name": "crm", "status": "ok", "detail": f"{len(deals)} open deals"})
        
        passed = sum(1 for c in checks if c["status"] == "ok")
        warnings = sum(1 for c in checks if c["status"] == "warning")
        errors = sum(1 for c in checks if c["status"] == "error")
        
        return {
            "checks": checks,
            "summary": {
                "passed": passed,
                "warnings": warnings,
                "errors": errors,
                "score": round(passed / len(checks) * 100, 1) if checks else 0,
            },
            "recommendations": self._generate_recommendations(checks),
        }

    def _generate_recommendations(self, checks: list[dict[str, Any]]) -> list[str]:
        """Generate recommendations based on audit results."""
        recs = []
        for check in checks:
            if check["status"] == "warning":
                if check["name"] == "knowledge":
                    recs.append("Run `geos knowledge ingest <dir>` to build knowledge base")
                elif check["name"] == "content":
                    recs.append("Review orphaned content ideas and either brief or archive them")
                elif check["name"] == "approvals":
                    recs.append("Review pending approvals to unblock automated workflows")
                elif check["name"] == "leads":
                    recs.append("Qualify or disqualify stale captured leads")
                elif check["name"] == "crm":
                    recs.append("Review low-probability deals or mark as LOST")
        return recs

    # ---- data ---------------------------------------------------------------
    def _metrics(self) -> dict[str, Any]:
        snapshot = self._repo.analytics.latest_snapshot()
        return (snapshot or {}).get("metrics") or {}

    def _insights(self) -> list[dict[str, Any]]:
        return self._repo.analytics.insights(limit=12)

    def _pending_approvals(self) -> list[dict[str, Any]]:
        return [a.__dict__ for a in self._repo.approvals.list_pending(limit=10)]

    def _runs(self) -> list[dict[str, Any]]:
        return [r.__dict__ for r in self._repo.runs.list(limit=8)]

    def _health(self) -> list[tuple[str, bool, str]]:
        checks: list[tuple[str, bool, str]] = []
        try:
            version = self._db.current_version()
            checks.append(("Schema", True, f"v{version}"))
        except Exception:  # noqa: BLE001
            checks.append(("Schema", False, "erro"))
        try:
            docs = self._repo.knowledge.list_documents()
            checks.append(("Knowledge", True, f"{len(docs)} documento(s)"))
        except Exception:  # noqa: BLE001
            checks.append(("Knowledge", False, "sem ingestão"))
        pending = self._repo.approvals.list_pending()
        checks.append(("Approvals", True, f"{len(pending)} pendente(s)"))
        return checks

    # ---- render -------------------------------------------------------------
    def render(self) -> str:
        m = self._metrics()
        insights = self._insights()
        approvals = self._pending_approvals()
        runs = self._runs()
        health = self._health()

        def kpi(label: str, value: Any, desc: str = "") -> str:
            return (f'<div class="kpi"><div class="v">{html.escape(str(value))}</div>'
                    f'<div class="l">{html.escape(label)}</div>'
                    f'<div class="d">{html.escape(desc)}</div></div>')

        content_total = m.get("content_total", 0)
        content_approved = m.get("content_approved", 0)
        content_published = m.get("content_published", 0)
        social_published = m.get("social_published", 0)
        social_pending = m.get("social_pending_approval", 0)
        blog_published = m.get("blog_published", 0)
        blog_pending = m.get("blog_pending_approval", 0)
        opportunities = m.get("opportunities_open", 0)
        experiments = m.get("experiments_running", 0)
        seo_critical = m.get("seo_issues_critical", 0)
        docs = len(self._repo.knowledge.list_documents())
        runs_total = m.get("workflow_runs", 0)

        kpis = "".join([
            kpi("Docs ingeridos", docs, "base de conhecimento local"),
            kpi("Conteúdo", content_total, f"{content_approved} aprovado · {content_published} publicado"),
            kpi("Blog", blog_published,
                f"{blog_pending} aguardando aprovação" if blog_pending else "sem pendências"),
            kpi("Social", social_published,
                f"{social_pending} aguardando aprovação" if social_pending else "sem pendências"),
            kpi("Oportunidades", opportunities, "abertas priorizadas"),
            kpi("Experimentos", experiments, "em execução"),
        ])

        insight_html = "".join(
            f'<div class="insight {html.escape(i["insight_type"])}">'
            f'<div class="t">{html.escape(i["insight_type"])}</div>'
            f'{html.escape(i["content"])}'
            + (f'<div class="e">evidência: {html.escape(i.get("evidence") or "")}</div>'
               if i.get("evidence") else "")
            + "</div>"
            for i in insights
        ) or '<div class="empty">Nenhum insight ainda — rode `geos analytics collect`.</div>'

        content_pct = _pct(content_published, content_total)
        pending_pct = _pct(content_approved + social_pending + blog_pending,
                           max(content_total, 1))
        distribution = "".join([
            _bar("Conteúdo publicado", content_pct),
            _bar("Conteúdo aguardando aprovação", pending_pct),
            _bar("SEO issues críticas", _pct(seo_critical, max(seo_critical, 1))),
        ])

        approval_html = "".join(
            f'<div class="row"><span class="n">{html.escape(a["action"])}'
            f'<small> — {a["id"][:8]} · {html.escape(str(a.get("risk") or ""))}</small></span>'
            f'<span class="badge warn">PENDING</span></div>'
            for a in approvals
        ) or '<div class="empty">Nenhuma aprovação pendente.</div>'

        health_html = "".join(
            f'<div class="row"><span class="n">{html.escape(name)}</span>'
            f'<span class="badge {"ok" if ok else "crit"}">{html.escape(detail)}</span></div>'
            for name, ok, detail in health
        )

        runs_html = "".join(
            f'<tr><td>{html.escape(r.get("workflow_id") or r.get("agent") or "-")}</td>'
            f'<td><span class="badge {"ok" if r["status"] == "SUCCESS" else "crit" if r["status"] == "FAILED" else "warn"}">'
            f'{html.escape(r["status"])}</span></td>'
            f'<td>{html.escape(str(r.get("started_at") or ""))[:19]}</td></tr>'
            for r in runs
        ) or '<div class="empty">Nenhum run registrado.</div>'

        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEOS Control Center</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>GEOS <span>Control&nbsp;Center</span></h1>
  <div class="meta">workspace · {html.escape(now_iso()[:19])}<br>
    <span class="pill ok">SPEC-038</span><span class="pill info">self-contained</span>
  </div>
</header>

<div class="grid kpi">{kpis}</div>

<div class="grid two">
  <div class="card"><h2>Insights</h2>{insight_html}</div>
  <div class="card">
    <h2>Distribuição</h2>{distribution}
    <h2 style="margin-top:18px">Aprovações pendentes</h2>{approval_html}
  </div>
</div>

<div class="grid two">
  <div class="card">
    <h2>Saúde do workspace</h2>{health_html}
    <h2 style="margin-top:18px">Runs recentes ({runs_total})</h2>
    <table><thead><tr><th>workflow</th><th>status</th><th>iniciado</th></tr></thead>
    <tbody>{runs_html}</tbody></table>
  </div>
  <div class="card">
    <h2>Métricas (último snapshot)</h2>
    {_metric_rows(m)}
  </div>
</div>

<footer>Gerado por GEOS (SPEC-038) · {html.escape(now_iso()[:19])} · determinístico, local-first</footer>
</body>
</html>
"""

    def build(self, output: str | Path) -> Path:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")
        return path


def _pct(part: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, int(round(part * 100 / total))))


def _bar(label: str, pct: int) -> str:
    color = "#34d399" if pct < 40 else "#fbbf24" if pct < 70 else "#f87171"
    return (f'<div class="row"><span class="n">{html.escape(label)} '
            f'<small>{pct}%</small></span></div>'
            f'<div class="bar"><i style="width:{pct}%;background:{color}"></i></div>')


def _metric_rows(metrics: dict[str, Any]) -> str:
    rows = []
    for name, value in sorted(metrics.items()):
        if value is None:
            value = "—"
        rows.append(f'<div class="row"><span class="n">{html.escape(name)}</span>'
                    f'<span>{html.escape(str(value))}</span></div>')
    return "".join(rows) or '<div class="empty">Rode `geos analytics collect` primeiro.</div>'
