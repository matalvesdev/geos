"""Opportunity & Experiment engine (SPEC-034).

Insights de research + gaps de SEO → oportunidades priorizadas (ICE/RICE explicáveis,
spec §102) → experimentos com hipótese, métricas, guardrails e aprendizado (spec §101).
Score auxilia, nunca substitui julgamento; breakdown + razões sempre registrados.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso, slugify

_EXPERIMENT_STATUSES = {"PROPOSED", "RUNNING", "COMPLETED", "CANCELLED"}
_DECISIONS = {"ADOPT", "REJECT", "ITERATE"}


class GrowthError(ValueError):
    """Invalid growth operation (bad transition, missing required field)."""


class OpportunityEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- collection --------------------------------------------------------
    def collect(self) -> dict[str, int]:
        """Create opportunities from research insights + SEO content gaps (dedup)."""
        created = {"research": 0, "seo": 0, "skipped": 0}
        open_refs = {
            r.get("source_ref") for r in self._repo.opportunities.list(status="OPEN")
        }
        # research insights (CONTENT_OPPORTUNITY / KNOWLEDGE_GAP opportunities)
        for row in self._repo.research.list(limit=200):
            full = self._repo.research.get(row["id"])
            for opp in full.get("opportunities") or []:
                problem = str(opp.get("content") or opp.get("type") or "").strip()
                if not problem:
                    continue
                # dedup per-problem: multiple opportunities in the same report
                # are distinct (SPEC-034 R2) — ref must include the problem.
                ref = f"research:{row['id']}:{slugify(problem)}"
                if ref in open_refs:
                    created["skipped"] += 1
                    continue
                self._repo.opportunities.create(
                    source="research", source_ref=ref, problem=problem,
                    evidence=row["id"], confidence=float(opp.get("confidence") or 0.5),
                    recommended_action="produzir conteúdo ou investigar",
                )
                open_refs.add(ref)
                created["research"] += 1
        # seo content gaps
        from .seo import SeoEngine

        for issue in SeoEngine(self._db).audit_content():
            if issue.category != "content_gap" or not issue.target:
                continue
            topic = str(issue.target).replace("TOPIC:", "")
            ref = f"seo:{topic.lower()}"
            if ref in open_refs:
                created["skipped"] += 1
                continue
            self._repo.opportunities.create(
                source="seo", source_ref=ref, problem=f"Tópico sem conteúdo: {topic}",
                evidence=issue.detail, confidence=0.5,
                recommended_action=f"geos content create \"{topic}\" --keywords \"{topic}\"",
            )
            open_refs.add(ref)
            created["seo"] += 1
        return created

    def create(self, problem: str, source: str = "manual", audience: str | None = None,
               evidence: str | None = None, impact: float | None = None,
               confidence: float | None = None, effort: float | None = None,
               reach: float | None = None, strategic_alignment: float | None = None,
               recommended_action: str | None = None) -> dict[str, Any]:
        problem = problem.strip()
        if not problem:
            raise GrowthError("problem is required")
        opportunity_id = self._repo.opportunities.create(
            source=source, problem=problem, audience=audience, evidence=evidence,
            impact=impact, confidence=confidence, effort=effort, reach=reach,
            strategic_alignment=strategic_alignment, recommended_action=recommended_action,
        )
        return self.get(opportunity_id)

    def update_components(self, opportunity_id: str, **components: Any) -> dict[str, Any]:
        self._repo.opportunities.update_components(opportunity_id, **components)
        return self.get(opportunity_id)

    def get(self, opportunity_id: str) -> dict[str, Any]:
        item = self._repo.opportunities.get(opportunity_id)
        if item is None:
            raise NotFoundError(f"opportunity {opportunity_id}")
        return item

    def list(self, method: str = "rice", top: int | None = None,
             status: str | None = None) -> list[dict[str, Any]]:
        items = self._repo.opportunities.list(status=status)
        scored = [self._ensure_score(i, method) for i in items]
        scored.sort(key=lambda i: (i.get("score") or 0.0), reverse=True)
        return scored[:top] if top else scored

    # ---- scoring (deterministic, explainable) ------------------------------
    def score(self, opportunity_id: str, method: str = "ice") -> dict[str, Any]:
        item = self.get(opportunity_id)
        self._ensure_score(item, method)
        return self.get(opportunity_id)

    def _ensure_score(self, item: dict[str, Any], method: str) -> dict[str, Any]:
        if method not in ("ice", "rice"):
            raise GrowthError(f"unknown scoring method {method!r} (ice|rice)")
        current_method = item.get("score_method")
        if current_method == method and item.get("score") is not None:
            return item
        if method == "ice":
            score, breakdown = _score_ice(item)
        else:
            score, breakdown = _score_rice(item)
        # persist component updates (reach may have been set on the item)
        self._repo.opportunities.update_components(
            item["id"], reach=item.get("reach"),
        )
        self._repo.opportunities.update_score(item["id"], score, method, breakdown)
        item["score"] = score
        item["score_method"] = method
        item["breakdown"] = breakdown
        return item


class ExperimentEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    def from_opportunity(self, opportunity_id: str, primary_metric: str,
                         change: str | None = None,
                         hypothesis: str | None = None) -> dict[str, Any]:
        opp = OpportunityEngine(self._db).get(opportunity_id)
        if opp["status"] != "OPEN":
            raise GrowthError(f"opportunity {opportunity_id} is {opp['status']}, not OPEN")
        problem = str(opp.get("problem") or "")
        audience = str(opp.get("audience") or "a definir")
        change = change or f"testar a oportunidade: {problem}"
        if not hypothesis:
            hypothesis = (
                f"Se {change}, então {primary_metric} melhora para {audience}, "
                f"porque as evidências ({opp.get('evidence') or 'sem evidência'}) "
                f"indicam interesse. Hipótese de template — a validar."
            )
        experiment_id = self._repo.experiments.create(
            opportunity_id=opportunity_id, problem=problem, hypothesis=hypothesis,
            primary_metric=primary_metric, change=change, audience=audience,
            evidence=opp.get("evidence"), confidence=opp.get("confidence"),
            effort=opp.get("effort"), expected_impact=opp.get("impact"),
        )
        self._repo.opportunities.update_status(opportunity_id, "EXPERIMENTING")
        try:
            SqliteEventBus(self._db).publish(
                "experiment.proposed",
                {"experiment_id": experiment_id, "opportunity_id": opportunity_id,
                 "primary_metric": primary_metric},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001 - telemetry must not fail creation
            pass
        return self.get(experiment_id)

    def get(self, experiment_id: str) -> dict[str, Any]:
        item = self._repo.experiments.get(experiment_id)
        if item is None:
            raise NotFoundError(f"experiment {experiment_id}")
        return item

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._repo.experiments.list(status=status, limit=limit)

    def transition(self, experiment_id: str, target: str) -> dict[str, Any]:
        item = self.get(experiment_id)
        target = target.upper()
        if target not in _EXPERIMENT_STATUSES:
            raise GrowthError(f"unknown experiment status {target!r}")
        allowed = {"PROPOSED": {"RUNNING", "CANCELLED"},
                   "RUNNING": {"COMPLETED", "CANCELLED"},
                   "COMPLETED": set(), "CANCELLED": set()}
        if target not in allowed[item["status"]]:
            raise GrowthError(
                f"invalid transition {item['status']} → {target} "
                f"(allowed: {sorted(allowed[item['status']]) or 'none'})"
            )
        self._repo.experiments.update_status(experiment_id, target)
        return self.get(experiment_id)

    def complete(self, experiment_id: str, result: str, analysis: str,
                 decision: str, learning: str) -> dict[str, Any]:
        item = self.get(experiment_id)
        if item["status"] != "RUNNING":
            raise GrowthError(f"only RUNNING experiments can be completed ({item['status']})")
        result = result.strip()
        learning = learning.strip()
        if not result or not learning:
            raise GrowthError("result and learning are required (SPEC-034 R4)")
        decision = decision.upper()
        if decision not in _DECISIONS:
            raise GrowthError(f"decision must be one of {sorted(_DECISIONS)}")
        self._repo.experiments.complete(experiment_id, result, analysis, decision, learning)
        try:
            SqliteEventBus(self._db).publish(
                "experiment.completed",
                {"experiment_id": experiment_id, "decision": decision},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass
        return self.get(experiment_id)


# ---------------------------------------------------------------------------
# Deterministic scoring math (spec §102). Components are 1–10 (ICE) or the
# RICE scales; breakdown records components + formula for explainability.
# ---------------------------------------------------------------------------
def _score_ice(item: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    impact = _clamp(item.get("impact"), 1, 10, 5)
    confidence = _clamp(item.get("confidence"), 1, 10, 5)
    effort = _clamp(item.get("effort"), 1, 10, 5)
    ease = round(10 - effort, 2)
    score = round((impact * confidence * ease) / 100, 3)
    breakdown = {
        "method": "ice", "formula": "ICE = Impact × Confidence × Ease / 100",
        "impact": impact, "confidence": confidence, "effort": effort, "ease": ease,
        "score": score,
        "reasons": {
            "impact": "default neutro (5) — informe impacto com base nas evidências",
            "confidence": "default neutro (5) — informe confiança na evidência",
            "effort": "default neutro (5) — estime o esforço em persona-dias",
        },
    }
    return score, breakdown


def _score_rice(item: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    reach = _clamp(item.get("reach"), 0, 100000, 100)
    impact = _clamp(item.get("impact"), 0.5, 3.0, 1.0)
    confidence = _clamp(item.get("confidence"), 0.5, 1.0, 0.8)
    effort = max(item.get("effort") or 1.0, 0.5)
    score = round((reach * impact * confidence) / effort, 3)
    breakdown = {
        "method": "rice", "formula": "RICE = Reach × Impact × Confidence / Effort",
        "reach": reach, "impact": impact, "confidence": confidence, "effort": effort,
        "score": score,
        "reasons": {
            "reach": "default 100 usuários/mês — informe alcance estimado",
            "impact": "default 1.0 (médio) — 0.5 baixo, 1 médio, 2 alto, 3 massivo",
            "confidence": "default 0.8 — reduza se a evidência for fraca",
        },
    }
    return score, breakdown


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))
