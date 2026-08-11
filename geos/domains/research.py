"""Research engine (SPEC-021): deterministic pipeline over the local knowledge base.

QUESTION → PLAN → SOURCES → EXTRACTION → SYNTHESIS → INSIGHT → KNOWLEDGE.
Sources are real (local index, with provenance). Synthesis is a deterministic template
marked `mock: True` by default; when a ModelProvider is configured, synthesis is
LLM-generated strictly from the retrieved sources (with citations), marked with the
model name and `mock: False`. Never invents facts (spec §56).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.events import SqliteEventBus
from ..core.models import ModelError, ModelProvider
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
    model: str | None = None
    provider: str | None = None
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "question": self.question, "status": self.status,
            "plan": self.plan, "sources": [s.to_dict() for s in self.sources],
            "extractions": self.extractions, "synthesis": self.synthesis,
            "insights": self.insights, "opportunities": self.opportunities,
            "mock": self.mock, "empty": self.empty, "model": self.model,
            "provider": self.provider, "created_at": self.created_at,
        }


_SYNTHESIS_SYSTEM_PROMPT = (
    "Você é o motor de síntese de pesquisa do GEOS. Sua tarefa: responder à pergunta "
    "do usuário EXCLUSIVAMENTE com base nas fontes fornecidas (marcadas [F1], [F2], ...). "
    "Regras: (1) não invente fatos, números ou citações que não estejam nas fontes; "
    "(2) use a linguagem da pergunta (PT-BR por padrão); (3) cite a fonte ao fim de cada "
    "afirmação no formato [F#]; (4) se as fontes não cobrem a pergunta, diga explicitamente "
    "o que não foi possível responder; (5) responda em parágrafos curtos, sem listas "
    "intermináveis; (6) nunca atribua causalidade sem evidência nas fontes."
)


class ResearchEngine:
    def __init__(self, db: Database, sources_limit: int = 5,
                 retriever: HybridRetriever | None = None,
                 model_provider: ModelProvider | None = None) -> None:
        self._db = db
        self._repo = RepoFactory(db)
        self._sources_limit = sources_limit
        self._retriever = retriever or HybridRetriever(db, config=RetrievalConfig())
        self._model_provider = model_provider

    def run(self, question: str, sources_limit: int | None = None,
            trace_id: str | None = None,
            model_provider: ModelProvider | None = None) -> ResearchReport:
        question = question.strip()
        if not question:
            raise ValueError("question is required")
        limit = sources_limit or self._sources_limit
        provider = model_provider if model_provider is not None else self._model_provider

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
        mock = True
        model: str | None = None
        model_provider_name: str | None = None
        if empty:
            synthesis = (
                f"Síntese determinística (mock) para '{question}': o índice local não "
                "retornou fontes — nenhuma fonte foi inventada. Indexe conhecimento com "
                "`geos knowledge ingest` antes de reexecutar."
            )
        elif provider is not None:
            synthesis, mock, model, model_provider_name = self._synthesize(
                provider, question, sources
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
            insights=insights, opportunities=opportunities, mock=mock, empty=empty,
            model=model, provider=model_provider_name,
        )
        self._persist(report, trace_id)
        return report

    def _synthesize(self, provider: ModelProvider, question: str,
                    sources: list[ResearchSource]) -> tuple[str, bool, str, str]:
        """LLM synthesis grounded strictly in the retrieved sources. On any model
        failure, falls back to the deterministic mock (research must not fail)."""
        context = "\n\n".join(
            f"[F{i + 1}] {s.title} ({s.uri})\n{s.snippet}"
            for i, s in enumerate(sources)
        )
        user_prompt = (
            f"Pergunta: {question}\n\n"
            f"Fontes:\n{context}\n\n"
            "Síntese (com citações [F#] e indicação explícita do que não foi possível "
            "responder):"
        )
        try:
            response = provider.complete(_SYNTHESIS_SYSTEM_PROMPT, user_prompt,
                                         temperature=0.2)
            synthesis = response.text.strip()
            if not synthesis:
                raise ModelError("model returned empty synthesis")
        except ModelError:
            # SPEC-039 R3: provider failure must never fail the research — the
            # deterministic mock (honest, no invented content) takes over.
            return (
                f"Síntese determinística (mock) para '{question}' — o ModelProvider "
                "falhou e o GEOS não fabricou conteúdo em seu lugar. As fontes abaixo "
                "podem ser usadas para síntese manual:\n"
                + "\n".join(f"- {s.title} ({s.uri})" for s in sources),
                True, None, None,
            )
        meta = provider.metadata()
        return synthesis, False, response.model, str(meta.get("provider") or "unknown")

    def _persist(self, report: ResearchReport, trace_id: str | None) -> None:
        self._repo.research.insert(
            research_id=report.id, question=report.question, status=report.status,
            plan=report.plan,
            sources=[s.to_dict() for s in report.sources],
            extractions=report.extractions, synthesis=report.synthesis,
            insights=report.insights, opportunities=report.opportunities,
            trace_id=trace_id, model=report.model, provider=report.provider,
            mock=report.mock,
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
