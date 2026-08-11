"""Content Engine (SPEC-022): content object lifecycle with deterministic scoring.

DISCOVER → IDEATE → SCORE → BRIEF → DRAFT → REVIEW → APPROVAL → SCHEDULE → PUBLISH →
MEASURE → REFRESH. All scoring is deterministic code (ADR-0004); drafts are template
mocks marked `mock: True` until a ModelProvider exists. Every transition is validated
and versioned (content_versions) for auditability.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso, slugify

CONTENT_TYPES = (
    "blog_post", "guide", "tutorial", "case_study", "comparison", "social_post",
    "carousel", "thread", "newsletter", "video_script", "short_video_script",
    "academy_lesson", "landing_page", "changelog", "announcement", "release_notes",
    "faq", "glossary",
)

# Deterministic pipeline statuses (SPEC-022 §70).
STATUS_FLOW: dict[str, set[str]] = {
    "IDEA": {"BRIEFED", "ARCHIVED"},
    "BRIEFED": {"DRAFTED", "ARCHIVED"},
    "DRAFTED": {"REVIEWING", "APPROVED", "ARCHIVED"},
    "REVIEWING": {"APPROVED", "ARCHIVED"},
    "APPROVED": {"SCHEDULED", "PUBLISHED", "ARCHIVED"},
    "SCHEDULED": {"PUBLISHED", "ARCHIVED"},
    "PUBLISHED": {"ARCHIVED"},
    "ARCHIVED": set(),
}

# Per-type distribution/effort heuristics (deterministic, configurable).
_TYPE_DISTRIBUTION = {
    "social_post": 0.9, "thread": 0.85, "carousel": 0.8, "newsletter": 0.7,
    "blog_post": 0.6, "guide": 0.6, "tutorial": 0.6, "landing_page": 0.6,
    "case_study": 0.5, "academy_lesson": 0.5, "video_script": 0.5,
}
_TYPE_EASE = {  # inverted effort: higher = cheaper to produce
    "social_post": 0.9, "thread": 0.85, "newsletter": 0.6, "blog_post": 0.6,
    "tutorial": 0.5, "case_study": 0.4, "guide": 0.4, "academy_lesson": 0.35,
    "landing_page": 0.5, "video_script": 0.4, "carousel": 0.7,
}

_NEUTRAL = 0.5  # honest neutral for dimensions without evidence


class ContentError(ValueError):
    """Invalid content operation (bad type, illegal transition)."""


class ContentEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)
        self._content = self._repo.content

    # ---- lifecycle ---------------------------------------------------------
    def create_idea(self, topic: str, content_type: str = "blog_post",
                    keywords: list[str] | None = None,
                    sources: list[str] | None = None,
                    source_workflow: str | None = None) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ContentError("topic is required")
        if content_type not in CONTENT_TYPES:
            raise ContentError(f"unknown content_type {content_type!r}")
        title = topic[0].upper() + topic[1:]
        slug = _unique_slug(self._content, slugify(topic))
        content_id = self._content.create(
            content_type=content_type, title=title, slug=slug, topic=topic,
            keywords=[k.strip() for k in (keywords or []) if k.strip()],
            sources=sources or [], mock=True, source_workflow=source_workflow,
        )
        self.score(content_id)
        try:
            SqliteEventBus(self._db).publish(
                "content.created",
                {"content_id": content_id, "topic": topic, "content_type": content_type},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001 - telemetry must not fail the create
            pass
        return self.get(content_id)

    def get(self, content_id: str) -> dict[str, Any]:
        item = self._content.get(content_id)
        if item is None:
            raise NotFoundError(f"content {content_id}")
        return item

    def list(self, status: str | None = None, content_type: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
        return self._content.list(status=status, content_type=content_type, limit=limit)

    # ---- scoring (SPEC-022 §72: deterministic components, no fixed weights) ----
    def score(self, content_id: str) -> dict[str, Any]:
        item = self.get(content_id)
        topic = str(item.get("topic") or "")
        keywords = [str(k) for k in (item.get("keywords") or [])]
        content_type = str(item.get("content_type") or "blog_post")

        topic_words = {w for w in topic.lower().replace("-", " ").split() if w}
        kw_words = set()
        for kw in keywords:
            kw_words.update(kw.lower().replace("-", " ").split())

        components: dict[str, float] = {
            "audience_fit": _NEUTRAL,
            "strategic_fit": _NEUTRAL,
            # search potential: keywords + topic length are the only signals we have
            "search_potential": min(1.0, _NEUTRAL + 0.1 * len(keywords) + (0.1 if topic else 0)),
            "educational_value": 0.6 if content_type in (
                "guide", "tutorial", "academy_lesson", "faq", "glossary") else _NEUTRAL,
            "product_relevance": _product_relevance(topic_words, kw_words),
            "novelty": 1.0 / (1.0 + self._topic_count(topic)),
            "distribution_potential": _TYPE_DISTRIBUTION.get(content_type, _NEUTRAL),
            "effort": _TYPE_EASE.get(content_type, _NEUTRAL),  # inverted: higher = cheaper
            "evergreen_potential": 0.8 if content_type not in (
                "announcement", "release_notes", "changelog") else 0.3,
        }
        composite = sum(components.values()) / len(components)
        with self._db.conn_checked:
            self._content.update(content_id, score=round(composite, 4),
                                 score_breakdown=components)
        return {"score": round(composite, 4), "breakdown": components,
                "confidence": 0.5}  # heuristic; never claim certainty

    def _topic_count(self, topic: str) -> int:
        if not topic:
            return 0
        row = self._db.conn_checked.execute(
            "SELECT COUNT(*) c FROM content WHERE lower(topic) = lower(?)", (topic,)
        ).fetchone()
        return int(row["c"])

    # ---- pipeline steps ----------------------------------------------------
    def write_brief(self, content_id: str, audience: str | None = None,
                    objective: str | None = None, cta: str | None = None,
                    persona: str | None = None, funnel_stage: str | None = None,
                    outline: list[str] | None = None) -> dict[str, Any]:
        item = self.get(content_id)
        if item["status"] != "IDEA":
            raise ContentError(f"cannot brief content in status {item['status']} (IDEA only)")
        topic = str(item.get("topic") or item["title"])
        brief = _build_brief(topic, item["content_type"], audience, objective,
                             cta, outline)
        self._content.update(
            content_id, status="BRIEFED", brief=brief, audience=audience,
            objective=objective, cta=cta, persona=persona, funnel_stage=funnel_stage,
        )
        return self.get(content_id)

    def produce_draft(self, content_id: str) -> dict[str, Any]:
        item = self.get(content_id)
        if item["status"] not in ("BRIEFED", "DRAFTED", "IDEA"):
            raise ContentError(f"cannot draft content in status {item['status']}")
        body = _build_draft(item)
        self._content.update(content_id, status="DRAFTED", body=body)
        self._content.snapshot_version(content_id)
        return self.get(content_id)

    def transition(self, content_id: str, target: str) -> dict[str, Any]:
        item = self.get(content_id)
        target = target.upper()
        allowed = STATUS_FLOW.get(item["status"], set())
        if target not in allowed:
            raise ContentError(
                f"invalid transition {item['status']} → {target} "
                f"(allowed: {sorted(allowed) or 'none'})"
            )
        self._content.update(content_id, status=target)
        try:
            SqliteEventBus(self._db).publish(
                "content.status_changed",
                {"content_id": content_id, "from": item["status"], "to": target},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass
        return self.get(content_id)

    # ---- repurposing (SPEC-022 §73: adapt, never copy mechanically) --------
    def repurpose(self, content_id: str, target_type: str) -> dict[str, Any]:
        if target_type not in CONTENT_TYPES:
            raise ContentError(f"unknown content_type {target_type!r}")
        item = self.get(content_id)
        body = str(item.get("body") or "")
        if not body:
            raise ContentError("source content has no draft body")
        variant_body = _repurpose_body(item, target_type)
        variant = self.create_idea(
            topic=f"{item['title']} ({target_type.replace('_', ' ')}) → repurposed",
            content_type=target_type,
            keywords=item.get("keywords") or [],
            sources=[*[str(s) for s in (item.get("sources") or [])],
                     f"repurposed-from:{content_id}"],
            source_workflow=item.get("source_workflow"),
        )
        variant_id = variant["id"]
        self._content.update(variant_id, status="DRAFTED", body=variant_body)
        self._content.snapshot_version(variant_id)
        return self.get(variant_id)


def _unique_slug(repo, base: str) -> str:
    candidate = base or "untitled"
    if repo.by_slug(candidate) is None:
        return candidate
    return f"{candidate}-{new_id()[:6]}"


def _product_relevance(topic_words: set[str], kw_words: set[str]) -> float:
    # Deterministic overlap signal: topic↔keyword vocabulary intersection.
    overlap = topic_words & kw_words
    if overlap:
        return min(1.0, 0.5 + 0.25 * len(overlap))
    return 0.4


def _build_brief(topic: str, content_type: str, audience: str | None,
                 objective: str | None, cta: str | None,
                 outline: list[str] | None) -> str:
    steps = outline or [
        f"O problema: {topic}",
        "Processo e evidência",
        "Como aplicar na operação",
        "Próximos passos",
    ]
    return (
        f"Brief determinístico (mock) para {content_type}: '{topic}'.\n"
        f"Audience: {audience or 'a definir'}. Objective: {objective or 'educate'}.\n"
        f"Outline:\n" + "\n".join(f"- {s}" for s in steps) +
        f"\nCTA: {cta or 'Falar com especialista'}"
    )


def _build_draft(item: dict[str, Any]) -> str:
    topic = str(item.get("topic") or item["title"])
    brief = str(item.get("brief") or "")
    return (
        f"# {item['title']}\n\n"
        f"Conteúdo determinístico (mock) sobre: {topic}.\n"
        f"Tipo: {item['content_type']} · Status: {item['status']}.\n\n"
        f"## Contexto\n{brief.splitlines()[0] if brief else ''}\n\n"
        f"## Estrutura\n1. O problema\n2. Processo e evidência\n3. Aplicação\n\n"
        f"_Este é um rascunho de template (mock: True); requer revisão humana e "
        f"fontes externas antes de qualquer uso externo._"
    )


def _repurpose_body(item: dict[str, Any], target_type: str) -> str:
    title = str(item["title"])
    topic = str(item.get("topic") or title)
    if target_type == "social_post":
        return (
            f"[mock-social] {topic} — aprendizado em uma linha. "
            f"Detalhes no artigo '{title}' (repurposed, mock: True)."
        )
    if target_type == "newsletter":
        return (
            f"[mock-newsletter] Tema: {topic}.\nResumo do artigo '{title}' + CTA. "
            f"(repurposed, mock: True)"
        )
    return (
        f"[mock-{target_type}] Variante de '{title}' sobre {topic}. "
        f"(repurposed, mock: True)"
    )
