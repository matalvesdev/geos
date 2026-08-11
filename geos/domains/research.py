"""Research engine (SPEC-021): deterministic pipeline over the local knowledge base.

QUESTION → PLAN → SOURCES → EXTRACTION → SYNTHESIS → INSIGHT → KNOWLEDGE.
Sources are real (local index, with provenance); synthesis is a deterministic template
marked `mock: True` until a ModelProvider exists. Never invents facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.events import SqliteEventBus
from ..intelligence.retrieval import HybridRetriever, RetrievalConfig, tokens_estimate
from ..storage.database import Database
from ..storage.repos import RepoFactory
from ..util import new_id, now_iso

_PLAN_TEMPLATE = [
    "context: enquadrar a pergunta no conhecimento organizacional",
    "discover: buscar fontes locais (FTS + vetores + graph)",
    "sources: selecionar e pontuar fontes com proveniência",
    "extract: extrair citações diretas com classificação",
    "synthesize: sintetizar (mock determinístico até existir ModelProvider)",
    "insights: registrar observações e hipóteses (nunca causalidade)",
]


@dataclass
class ResearchSource:
    uri: str
    title: str
    snippet: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"uri": self.uri, "title": self.title, "snippet": self.snippet,
                "score": round(self.score, 4)}


@dataclass
class ResearchReport:
    id: str
    question: str
    status: str
    plan: list[str]
    sources: list[ResearchSource]
    extractions: list[dict[str, Any]]
    synthesis: str
    insights: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    mock: bool = True
    empty: bool = False
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "question": self.question, "status": self.status,
            "plan": self.plan, "sources": [s.to_dict() for s in self.sources],
            "extractions": self.extractions, "synthesis": self.synthesis,
            "insights": self.insights, "opportunities": self.opportunities,
            "mock": self.mock, "empty": self.empty, "created_at": self.created_at,
        }


class ResearchEngine:
    def __init__(self, db: Database, sources_limit: int = 5,
                 retriever: HybridRetriever | None = None) -> None:
        self._db = db
        self._repo = RepoFactory(db)
        self._sources_limit = sources_limit
        self._retriever = retriever or HybridRetriever(db, config=RetrievalConfig())

    def run(self, question: str, sources_limit: int | None = None,
            trace_id: str | None = None) -> ResearchReport:
        question = question.strip()
        if not question:
            raise ValueError("question is required")
        limit = sources_limit or self._sources_limit

        hits = self._retriever.search(question, limit=limit)
        sources = [
            ResearchSource(uri=h.uri, title=h.title, snippet=h.snippet, score=h.score)
            for h in hits
        ]
        extractions = [
            {"quote": h.snippet[:180], "classification": "SOURCE_QUOTE",
             "evidence": h.uri, "title": h.title}
            for h in hits[: min(3, len(hits))]
        ]

        empty = not sources
        if empty:
            synthesis = (
                f"Síntese determinística (mock) para '{question}': o índice local não "
                "retornou fontes — nenhuma fonte foi inventada. Indexe conhecimento com "
                "`geos knowledge ingest` antes de reexecutar."
            )
        else:
            bullets = "\n".join(f"- {s.title} ({s.uri})" for s in sources)
            synthesis = (
                f"Síntese determinística (mock) para '{question}'.\n"
                f"O conhecimento indexado retorna {len(sources)} fonte(s):\n{bullets}\n"
                "Isto é uma síntese de template; requer revisão humana e fontes externas "
                "antes de qualquer uso externo (mock=True)."
            )

        insights: list[dict[str, Any]] = []
        if sources:
            insights.append(
                {"type": "OBSERVATION",
                 "content": f"O conhecimento local associa '{question}' principalmente a "
                            f"{sources[0].title}.",
                 "evidence": sources[0].uri, "confidence": 0.6}
            )
            insights.append(
                {"type": "HYPOTHESIS",
                 "content": f"Conteúdo sobre '{question}' com foco em processo/evidência "
                            f"pode ter demanda (hipótese a validar).",
                 "evidence": sources[0].uri, "confidence": 0.3,
                 "needs_validation": True}
            )
        else:
            insights.append(
                {"type": "OBSERVATION",
                 "content": f"Sem conhecimento indexado sobre '{question}' — gap de "
                            f"conhecimento identificado.",
                 "evidence": None, "confidence": 0.9}
            )

        opportunities = [
            {"type": "KNOWLEDGE_GAP" if empty else "CONTENT_OPPORTUNITY",
             "content": f"Produzir/reforçar material sobre '{question}'.",
             "confidence": 0.5}
        ]

        report = ResearchReport(
            id=new_id(), question=question, status="COMPLETED", plan=list(_PLAN_TEMPLATE),
            sources=sources, extractions=extractions, synthesis=synthesis,
            insights=insights, opportunities=opportunities, mock=True, empty=empty,
        )
        self._persist(report, trace_id)
        return report

    def _persist(self, report: ResearchReport, trace_id: str | None) -> None:
        self._repo.research.insert(
            research_id=report.id, question=report.question, status=report.status,
            plan=report.plan,
            sources=[s.to_dict() for s in report.sources],
            extractions=report.extractions, synthesis=report.synthesis,
            insights=report.insights, opportunities=report.opportunities,
            trace_id=trace_id,
        )
        for insight in report.insights:
            insight_id = new_id()
            self._repo.research.insert_insight(
                insight_id=insight_id, research_id=report.id,
                insight_type=str(insight.get("type", "INSIGHT")),
                content=str(insight.get("content", "")),
                evidence=insight.get("evidence"), confidence=insight.get("confidence"),
                source="research",
            )
            self._repo.knowledge.upsert_node(
                "INSIGHT", str(insight.get("content", ""))[:120],
                canonical_name=None, description=str(insight.get("content", "")),
                confidence=insight.get("confidence"), source=f"research:{report.id}",
                metadata={"research_id": report.id, "type": insight.get("type")},
            )
        try:
            SqliteEventBus(self._db).publish(
                "research.completed",
                {"research_id": report.id, "question": report.question,
                 "sources": len(report.sources), "empty": report.empty},
                trace_id=trace_id,
            )
        except Exception:  # noqa: BLE001 - telemetry must not fail the research
            pass

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._repo.research.list(limit=limit)

    def get(self, research_id: str) -> dict[str, Any] | None:
        return self._repo.research.get(research_id)


def estimate_context_tokens(synthesis: str, sources: list[dict[str, Any]]) -> int:
    chars = len(synthesis) + sum(len(str(s.get("snippet", ""))) for s in sources)
    return tokens_estimate(chars)
