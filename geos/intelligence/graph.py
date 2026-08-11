"""Knowledge graph engine (SPEC-013): rule-based deterministic extraction on SQLite
nodes/edges + graph queries. Recall is deliberately modest; confidence and provenance
are always recorded (no LLM in bootstrap, ADR-0004)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..storage.database import Database
from ..storage.repos import KnowledgeRepository
from ..util import slugify

# Default entity dictionary: name -> node_type (configurable via RuleBasedExtractor arg).
DEFAULT_ENTITIES: dict[str, str] = {
    "Azeetra": "COMPANY",
    "Zetra": "COMPANY",
    "Zetra One": "PRODUCT",
    "Trusted Origin": "PRODUCT",
    "Decision Intelligence": "CATEGORY",
    "Cash Application": "DOMAIN",
    "GEOS": "PRODUCT",
    "conciliação bancária": "TOPIC",
    "conciliação": "TOPIC",
    "origem de crédito": "TOPIC",
    "cash application": "TOPIC",
    "reconciliação": "TOPIC",
    "crédito não identificado": "PROBLEM",
    "de onde veio esse dinheiro": "PROBLEM",
    "de onde veio esse crédito": "PROBLEM",
    "origem desconhecida": "PROBLEM",
}

# Patterns for deterministic candidate extraction. No free capitalized-phrase guessing:
# dictionary + keyword/problem lists only (avoids noisy COMPANY nodes, ADR-0004).
_PROBLEM_PHRASES = (
    "não conciliad", "não identificad", "sem origem", "origem desconhecida",
    "de onde veio", "não bate", "discrepânc",
)
_TOPIC_KEYWORDS = (
    "conciliação", "crédito", "origem", "recebíveis", "pix", "extrato", "cash application",
    "reconciliação", "documento", "evidência", "auditoria", "fluxo", "processo",
)

_MIN_COOCCURRENCE = 2  # chunks before a TOPIC→TOPIC edge is created


@dataclass
class ExtractionResult:
    nodes: int = 0
    edges: int = 0
    entities: list[tuple[str, str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges, "entities": self.entities}


class RuleBasedExtractor:
    def __init__(self, entities: dict[str, str] | None = None) -> None:
        merged = dict(DEFAULT_ENTITIES)
        if entities:
            merged.update(entities)
        self._entities = merged
        # index for substring matching
        self._names = sorted(merged, key=len, reverse=True)

    def extract(self, text: str) -> list[tuple[str, str, float]]:
        """Return [(node_type, name, confidence)] in document order."""
        found: dict[tuple[str, str], float] = {}
        lowered = text.lower()
        for name in self._names:
            if name.lower() in lowered:
                node_type = self._entities[name]
                confidence = 0.9 if len(name) >= 4 else 0.7
                found[(node_type, name)] = max(found.get((node_type, name), 0.0), confidence)
        # PROBLEM phrases
        for phrase in _PROBLEM_PHRASES:
            if phrase in lowered:
                found.setdefault(("PROBLEM", phrase), 0.6)
        # TOPIC keywords
        for keyword in _TOPIC_KEYWORDS:
            if keyword in lowered:
                found.setdefault(("TOPIC", keyword), 0.5)
        return [(node_type, name, conf) for (node_type, name), conf in found.items()]

    def process_document(self, db: Database, document_id: str, uri: str,
                         title: str, chunks: list[dict[str, Any]]) -> ExtractionResult:
        """Upsert CONTENT node + entities + edges for one document's chunks."""
        repo = KnowledgeRepository(db)
        result = ExtractionResult()
        content_node = repo.upsert_node(
            "CONTENT", title or uri, canonical_name=slugify(title or uri),
            description=f"Documento: {uri}", confidence=1.0, source=uri,
            metadata={"uri": uri},
        )
        result.nodes += 1

        topic_counts: dict[str, int] = {}
        chunk_topic_map: dict[str, set[str]] = {}
        for chunk in chunks:
            content = str(chunk.get("content") or "")
            entities = self.extract(content)
            chunk_topics = set()
            for node_type, name, confidence in entities:
                node_id = repo.upsert_node(
                    node_type, name, canonical_name=slugify(name), confidence=confidence,
                    source=uri, metadata={"document": uri},
                )
                if node_type == "TOPIC":
                    topic_counts[name] = topic_counts.get(name, 0) + 1
                    chunk_topics.add(name)
                result.nodes += 1
                repo.upsert_edge(content_node, node_id, "discusses", weight=confidence,
                                 confidence=confidence, source=uri)
                result.edges += 1
            if chunk_topics:
                chunk_topic_map[chunk.get("chunk_id", "")] = chunk_topics

        # TOPIC → relates_to → TOPIC on co-occurrence across chunks
        for topics in chunk_topic_map.values():
            topic_list = sorted(topics)
            for i in range(len(topic_list)):
                for j in range(i + 1, len(topic_list)):
                    a, b = topic_list[i], topic_list[j]
                    if topic_counts.get(a, 0) >= _MIN_COOCCURRENCE and topic_counts.get(b, 0) >= _MIN_COOCCURRENCE:
                        na = repo.upsert_node("TOPIC", a, canonical_name=slugify(a),
                                              confidence=0.5, source=uri)
                        nb = repo.upsert_node("TOPIC", b, canonical_name=slugify(b),
                                              confidence=0.5, source=uri)
                        repo.upsert_edge(na, nb, "relates_to", weight=0.5,
                                         confidence=0.4, source=uri)
                        result.edges += 1
        return result


class GraphService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = KnowledgeRepository(db)

    def nodes_by_type(self, node_type: str, limit: int = 500) -> list[dict[str, Any]]:
        return self._repo.list_nodes(node_type=node_type, limit=limit)

    def related_documents(self, topics: list[str], limit: int = 50) -> list[str]:
        """URIs of documents that discuss any of the given TOPIC names (single JOIN)."""
        if not topics:
            return []
        rows = self._repo.list_nodes(node_type="TOPIC", limit=500)
        topic_ids = [r["id"] for r in rows if r.get("name") in topics]
        if not topic_ids:
            return []
        placeholders = ",".join("?" for _ in topic_ids)
        rows = self._db.conn_checked.execute(
            "SELECT n.metadata FROM knowledge_edges e"
            " JOIN knowledge_nodes n ON n.id = e.source_node"
            " WHERE e.relationship = 'discusses' AND e.target_node IN (" + placeholders + ")"
            " LIMIT ?",
            [*topic_ids, limit],
        ).fetchall()
        import json

        uris: list[str] = []
        seen: set[str] = set()
        for row in rows:
            raw = row["metadata"]
            try:
                meta = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                meta = {}
            uri = meta.get("uri")
            if uri and uri not in seen:
                seen.add(uri)
                uris.append(uri)
        return uris

    def neighbors(self, node_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT source_node, target_node, relationship, weight FROM knowledge_edges"
            " WHERE source_node = ? OR target_node = ? LIMIT ?",
            (node_id, node_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        conn = self._db.conn_checked
        nodes = int(conn.execute("SELECT COUNT(*) c FROM knowledge_nodes").fetchone()["c"])
        edges = int(conn.execute("SELECT COUNT(*) c FROM knowledge_edges").fetchone()["c"])
        by_type = {
            row["node_type"]: int(row["c"])
            for row in conn.execute(
                "SELECT node_type, COUNT(*) c FROM knowledge_nodes GROUP BY node_type"
            ).fetchall()
        }
        return {"nodes": nodes, "edges": edges, "by_type": by_type}

    def _node_by_id(self, node_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM knowledge_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return dict(row) if row else None
