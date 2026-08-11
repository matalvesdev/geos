"""Analytics engine (SPEC-035): deterministic metric registry + insights.

Metrics are computed exclusively from what GEOS already knows (content, blog,
social, seo, growth, research, telemetry) — never fabricated, never guessed.
A snapshot persists all metrics + summary for history; rule-based insights turn
metrics into OBSERVATION (fact), HYPOTHESIS (testable, low-confidence honest),
and INVESTIGATION (follow-up needed) items.
"""

from __future__ import annotations

from typing import Any, Callable

from ..storage.database import Database
from ..storage.repos import RepoFactory
from ..util import now_iso

INSIGHT_TYPES = ("OBSERVATION", "HYPOTHESIS", "INVESTIGATION")


class AnalyticsError(ValueError):
    """Invalid analytics operation (unknown insight type, empty snapshot)."""


def _count(db: Database, table: str, where: str = "", params: tuple = ()) -> int:
    q = f"SELECT COUNT(*) c FROM {table}"
    if where:
        q += f" WHERE {where}"
    return int(db.conn_checked.execute(q, params).fetchone()["c"])


# ---------------------------------------------------------------------------
# Deterministic metric registry (SPEC-035 R1): each metric is a named function
# over local tables, with an honest description. No external data, no estimates.
# ---------------------------------------------------------------------------
def _metric_definition(name: str, domain: str, description: str,
                       fn: Callable[[Database], float | int]) -> dict[str, Any]:
    return {"name": name, "domain": domain, "description": description, "fn": fn}


def _build_registry() -> list[dict[str, Any]]:
    return [
        _metric_definition("content_total", "content", "Objetos de conteúdo criados",
                           lambda db: _count(db, "content")),
        _metric_definition("content_approved", "content",
                           "Conteúdo aprovado aguardando distribuição",
                           lambda db: _count(db, "content", "status = 'APPROVED'")),
        _metric_definition("content_published", "content", "Conteúdo publicado",
                           lambda db: _count(db, "content", "status = 'PUBLISHED'")),
        _metric_definition("content_avg_score", "content",
                           "Score médio (determinístico) dos conteúdos",
                           lambda db: _avg_score(db)),
        _metric_definition("blog_posts", "blog", "Posts de blog preparados",
                           lambda db: _count(db, "blog_posts")),
        _metric_definition("blog_published", "blog", "Posts de blog publicados",
                           lambda db: _count(db, "blog_posts", "status = 'PUBLISHED'")),
        _metric_definition("blog_pending_approval", "blog",
                           "Posts de blog aguardando aprovação humana",
                           lambda db: _count(db, "blog_posts",
                                             "status = 'APPROVAL_PENDING'")),
        _metric_definition("social_posts", "social", "Posts sociais preparados",
                           lambda db: _count(db, "social_posts")),
        _metric_definition("social_published", "social", "Posts sociais publicados",
                           lambda db: _count(db, "social_posts", "status = 'PUBLISHED'")),
        _metric_definition("social_scheduled", "social", "Posts sociais agendados",
                           lambda db: _count(db, "social_posts", "status = 'SCHEDULED'")),
        _metric_definition("social_pending_approval", "social",
                           "Posts sociais aguardando aprovação humana",
                           lambda db: _count(db, "social_posts",
                                             "status = 'APPROVAL_PENDING'")),
        _metric_definition("social_due", "social",
                           "Posts sociais agendados cuja janela já venceu",
                           lambda db: _count(db, "social_posts",
                                             "status = 'SCHEDULED' AND scheduled_at IS NOT NULL"
                                             " AND scheduled_at <= ?", (now_iso(),))),
        _metric_definition("seo_issues_total", "seo", "Issues de SEO registradas",
                           lambda db: _count(db, "seo_issues")),
        _metric_definition("seo_issues_critical", "seo",
                           "Issues críticas de SEO",
                           lambda db: _count(db, "seo_issues", "severity = 'critical'")),
        _metric_definition("opportunities_open", "growth",
                           "Oportunidades abertas priorizadas",
                           lambda db: _count(db, "opportunities", "status = 'OPEN'")),
        _metric_definition("experiments_running", "growth", "Experimentos em execução",
                           lambda db: _count(db, "experiments", "status = 'RUNNING'")),
        _metric_definition("experiments_completed", "growth", "Experimentos concluídos",
                           lambda db: _count(db, "experiments", "status = 'COMPLETED'")),
        _metric_definition("research_runs", "research", "Runs de research executados",
                           lambda db: _count(db, "research")),
        _metric_definition("insights_total", "research", "Insights gerados por research",
                           lambda db: _count(db, "insights")),
        _metric_definition("workflow_runs", "telemetry", "Runs de workflow registrados",
                           lambda db: _count(db, "runs")),
        _metric_definition("workflow_failures", "telemetry",
                           "Runs de workflow com falha",
                           lambda db: _count(db, "runs", "status = 'FAILED'")),
    ]


def _avg_score(db: Database) -> float:
    row = db.conn_checked.execute(
        "SELECT AVG(score) s FROM content WHERE score IS NOT NULL"
    ).fetchone()
    if row is None or row["s"] is None:
        return 0.0
    return round(float(row["s"]), 4)


# ---------------------------------------------------------------------------
# Rule-based insights (SPEC-035 R2): deterministic, evidence-backed, honest.
# ---------------------------------------------------------------------------
class _Insight:
    def __init__(self, insight_type: str, content: str, severity: str = "info",
                 evidence: str | None = None, confidence: float | None = None) -> None:
        if insight_type not in INSIGHT_TYPES:
            raise AnalyticsError(f"unknown insight type {insight_type!r}")
        self.insight_type = insight_type
        self.content = content
        self.severity = severity
        self.evidence = evidence
        self.confidence = confidence


def _int_or_zero(value: Any) -> int:
    """Metrics may be None when a metric function failed (resilience, SPEC-035 R4)."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _derive_insights(m: dict[str, Any]) -> list[_Insight]:
    insights: list[_Insight] = []

    pending_social = _int_or_zero(m.get("social_pending_approval"))
    if pending_social:
        insights.append(_Insight(
            "OBSERVATION",
            f"{pending_social} post(s) social(is) aguardam aprovação humana",
            severity="warning",
            evidence=f"social_posts status=APPROVAL_PENDING ({pending_social})"))
    pending_blog = _int_or_zero(m.get("blog_pending_approval"))
    if pending_blog:
        insights.append(_Insight(
            "OBSERVATION",
            f"{pending_blog} post(s) de blog aguardam aprovação humana",
            severity="warning",
            evidence=f"blog_posts status=APPROVAL_PENDING ({pending_blog})"))

    due = _int_or_zero(m.get("social_due"))
    if due:
        insights.append(_Insight(
            "INVESTIGATION",
            f"{due} post(s) social(is) agendado(s) já têm a janela vencida — "
            f"publicar com `geos social publish <id> --approve`",
            severity="warning",
            evidence=f"social_posts status=SCHEDULED vencidos ({due})"))

    critical = _int_or_zero(m.get("seo_issues_critical"))
    if critical:
        insights.append(_Insight(
            "INVESTIGATION",
            f"{critical} issue(s) crítica(s) de SEO pendente(s) — revisar auditoria",
            severity="critical",
            evidence=f"seo_issues severity=critical ({critical})"))

    published = _int_or_zero(m.get("social_published"))
    if published and not due:
        insights.append(_Insight(
            "HYPOTHESIS",
            "Posts sociais publicados podem gerar tráfego e sinais — a medir via "
            "engagement quando houver adapters de métricas reais",
            severity="info",
            evidence=f"social_published={published}",
            confidence=0.3))  # honest low confidence

    open_opps = _int_or_zero(m.get("opportunities_open"))
    if open_opps:
        insights.append(_Insight(
            "OBSERVATION",
            f"{open_opps} oportunidade(s) priorizada(s) aberta(s) — considerar "
            f"transformar as top em experimentos",
            evidence=f"opportunities status=OPEN ({open_opps})"))

    completed = _int_or_zero(m.get("experiments_completed"))
    running = _int_or_zero(m.get("experiments_running"))
    if running:
        insights.append(_Insight(
            "OBSERVATION",
            f"{running} experimento(s) em execução — concluir com decisão e learning",
            evidence=f"experiments status=RUNNING ({running})"))
    if completed and not running:
        insights.append(_Insight(
            "HYPOTHESIS",
            "Com experimentos concluídos e nenhum em execução, há capacidade para "
            "novos testes — priorizar oportunidades abertas",
            evidence=f"experiments_completed={completed}, running=0",
            confidence=0.3))

    fails = _int_or_zero(m.get("workflow_failures"))
    runs_total = _int_or_zero(m.get("workflow_runs"))
    if fails and runs_total:
        rate = fails / runs_total
        if rate >= 0.1:
            insights.append(_Insight(
                "INVESTIGATION",
                f"{fails}/{runs_total} runs de workflow falharam ({rate:.0%}) — "
                f"investigar jobs em dead-letter",
                severity="warning",
                evidence=f"runs status=FAILED ({fails})"))

    if not insights:
        insights.append(_Insight(
            "OBSERVATION",
            "Sem pendências de aprovação, vencimentos ou falhas — operação limpa",
            evidence="nenhuma métrica de atenção disparou"))
    return insights


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class AnalyticsEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    def collect(self) -> dict[str, Any]:
        """Compute + persist a metric snapshot with derived insights."""
        registry = _build_registry()
        metrics: dict[str, Any] = {}
        domains: dict[str, list[str]] = {}
        for definition in registry:
            name = definition["name"]
            try:
                metrics[name] = definition["fn"](self._db)
            except Exception as exc:  # noqa: BLE001 - one bad metric never fails the run
                metrics[name] = None
            domains.setdefault(definition["domain"], []).append(name)
        summary = {
            "domains": {d: sorted(n) for d, n in domains.items()},
            "count": len(metrics),
            "at": now_iso(),
        }
        snapshot_id = self._repo.analytics.create_snapshot(metrics, summary)
        insights = _derive_insights(metrics)
        for insight in insights:
            self._repo.analytics.insert_insight(
                snapshot_id, insight.insight_type, insight.content,
                insight.severity, insight.evidence, insight.confidence,
            )
        return {
            "snapshot_id": snapshot_id, "metrics": metrics, "summary": summary,
            "insights": [vars(i) for i in insights],
        }

    def metrics(self, domain: str | None = None) -> dict[str, Any]:
        snapshot = self._repo.analytics.latest_snapshot()
        if snapshot is None:
            raise AnalyticsError("no snapshot yet — run `geos analytics collect` first")
        metrics = snapshot["metrics"]
        if domain:
            registry = {d["name"]: d for d in _build_registry()}
            metrics = {n: v for n, v in metrics.items()
                       if n in registry and registry[n]["domain"] == domain}
        return metrics

    def insights(self, insight_type: str | None = None) -> list[dict[str, Any]]:
        return self._repo.analytics.insights(insight_type=insight_type)

    def latest(self) -> dict[str, Any] | None:
        return self._repo.analytics.latest_snapshot()
