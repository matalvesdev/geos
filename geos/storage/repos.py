"""Repository layer (SPEC-003). Domains depend on these, never on SQLite directly."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from ..util import new_id, now_iso, slugify

from .database import Database


class DuplicateKeyError(Exception):
    """Unique-constraint violation surfaced as a typed error."""


class NotFoundError(Exception):
    """Requested entity does not exist."""


# ---------------------------------------------------------------- Run (SPEC-001)
@dataclass
class Run:
    id: str
    workspace_id: str
    trace_id: str
    status: str
    started_at: str
    workflow_id: str | None = None
    agent: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    model: str | None = None
    tokens: int | None = None
    cost: float | None = None
    error: str | None = None


class RunRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, run: Run) -> Run:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO runs (id, workspace_id, workflow_id, agent, trace_id, status,"
                " started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run.id, run.workspace_id, run.workflow_id, run.agent, run.trace_id,
                 run.status, run.started_at),
            )
        return run

    def get(self, run_id: str) -> Run | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return self._row_to_run(row) if row else None

    def finish(
        self,
        run_id: str,
        status: str,
        error: str | None = None,
        model: str | None = None,
        tokens: int | None = None,
        cost: float | None = None,
    ) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE runs SET status = ?, error = ?, finished_at = ?,"
                " duration_ms = CAST((julianday('now') - julianday(substr(started_at,1,19)))"
                " * 86400000 AS INTEGER), model = ?, tokens = ?, cost = ? WHERE id = ?",
                (status, error, now_iso(), model, tokens, cost, run_id),
            )

    def list(self, status: str | None = None, limit: int = 100) -> list[Run]:
        q = "SELECT * FROM runs"
        params: list[Any] = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [self._row_to_run(r) for r in rows]

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"], workspace_id=row["workspace_id"], workflow_id=row["workflow_id"],
            agent=row["agent"], trace_id=row["trace_id"], status=row["status"],
            started_at=row["started_at"], finished_at=row["finished_at"],
            duration_ms=row["duration_ms"], model=row["model"], tokens=row["tokens"],
            cost=row["cost"], error=row["error"],
        )


# ---------------------------------------------------------------- Events (SPEC-004)
@dataclass
class Event:
    event_type: str
    payload: dict[str, Any]
    id: str = field(default_factory=new_id)
    trace_id: str | None = None
    created_at: str = field(default_factory=now_iso)


class EventRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, event: Event) -> Event:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO events (id, event_type, payload, trace_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (event.id, event.event_type, json.dumps(event.payload, ensure_ascii=False),
                 event.trace_id, event.created_at),
            )
        return event

    def list(self, event_type: str | None = None, trace_id: str | None = None,
             limit: int = 100) -> list[Event]:
        q = "SELECT * FROM events"
        clauses: list[str] = []
        params: list[Any] = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if trace_id:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [
            Event(
                id=r["id"], event_type=r["event_type"],
                payload=json.loads(r["payload"]), trace_id=r["trace_id"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def count(self, event_type: str | None = None) -> int:
        q = "SELECT COUNT(*) c FROM events"
        params: list[Any] = []
        if event_type:
            q += " WHERE event_type = ?"
            params.append(event_type)
        return int(self._db.conn_checked.execute(q, params).fetchone()["c"])


# ---------------------------------------------------------------- Jobs (SPEC-005)
@dataclass
class Job:
    id: str
    kind: str
    payload: dict[str, Any]
    status: str
    idempotency_key: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    run_after: str | None = None
    last_error: str | None = None
    trace_id: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


class JobRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        run_after: str | None = None,
        max_attempts: int = 3,
        trace_id: str | None = None,
    ) -> Job:
        job = Job(
            id=new_id(), kind=kind, payload=payload, status="PENDING",
            idempotency_key=idempotency_key, run_after=run_after,
            max_attempts=max_attempts, trace_id=trace_id,
        )
        try:
            with self._db.conn_checked:
                self._db.conn_checked.execute(
                    "INSERT INTO jobs (id, idempotency_key, kind, payload, status, attempts,"
                    " max_attempts, run_after, trace_id, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (job.id, job.idempotency_key, job.kind,
                     json.dumps(payload, ensure_ascii=False), job.status, job.attempts,
                     job.max_attempts, job.run_after, job.trace_id,
                     job.created_at, job.updated_at),
                )
        except sqlite3.IntegrityError as exc:
            if idempotency_key:
                existing = self.by_idempotency(idempotency_key)
                if existing is not None:
                    return existing  # idempotent success (SPEC-005 R5.2)
            raise DuplicateKeyError(f"job already exists: {idempotency_key}") from exc
        return job

    def by_idempotency(self, key: str) -> Job | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM jobs WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return self._row_to_job(row) if row else None

    def claim_next(self, now: str) -> Job | None:
        """Atomically claim the oldest due PENDING job (single-writer, BEGIN IMMEDIATE)."""
        conn = self._db.conn_checked
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status IN ('PENDING', 'RETRYING')"
                " AND (run_after IS NULL OR run_after <= ?) ORDER BY created_at LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            job = self._row_to_job(row)
            conn.execute(
                "UPDATE jobs SET status = 'RUNNING', updated_at = ? WHERE id = ?",
                (now, job.id),
            )
        job.status = "RUNNING"
        return job

    def update_status(
        self, job_id: str, status: str, error: str | None = None, run_after: str | None = None
    ) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE jobs SET status = ?, last_error = ?, run_after = ?, updated_at = ?"
                " WHERE id = ?",
                (status, error, run_after, now_iso(), job_id),
            )

    def increment_attempts(self, job_id: str) -> int:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE jobs SET attempts = attempts + 1, updated_at = ? WHERE id = ?",
                (now_iso(), job_id),
            )
        row = self._db.conn_checked.execute(
            "SELECT attempts FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return int(row["attempts"])

    def list(self, status: str | None = None, limit: int = 100) -> list[Job]:
        q = "SELECT * FROM jobs"
        params: list[Any] = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [self._row_to_job(r) for r in rows]

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"], kind=row["kind"], payload=json.loads(row["payload"]),
            status=row["status"], idempotency_key=row["idempotency_key"],
            attempts=row["attempts"], max_attempts=row["max_attempts"],
            run_after=row["run_after"], last_error=row["last_error"],
            trace_id=row["trace_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ---------------------------------------------------------------- Approvals (SPEC-019 DDL)
@dataclass
class Approval:
    id: str
    action: str
    status: str
    agent: str | None = None
    risk: str | None = None
    requested_at: str = field(default_factory=now_iso)
    decided_at: str | None = None
    decision: str | None = None
    decided_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ApprovalRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def request(self, action: str, agent: str | None = None, risk: str | None = None,
                metadata: dict[str, Any] | None = None) -> Approval:
        approval = Approval(
            id=new_id(), action=action, status="PENDING", agent=agent, risk=risk,
            metadata=metadata or {},
        )
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO approvals (id, action, agent, risk, status, requested_at, metadata)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (approval.id, approval.action, approval.agent, approval.risk,
                 approval.status, approval.requested_at,
                 json.dumps(approval.metadata, ensure_ascii=False)),
            )
        return approval

    def list_pending(self, limit: int = 100) -> list[Approval]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM approvals WHERE status = 'PENDING'"
            " ORDER BY requested_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_approval(r) for r in rows]

    def get(self, approval_id: str) -> Approval | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        return self._row_to_approval(row) if row else None

    # decision -> status mapping (approve→APPROVED, reject→REJECTED, recorded→RECORDED)
    _DECISION_STATUS = {"approve": "APPROVED", "reject": "REJECTED", "recorded": "RECORDED"}

    def decide(self, approval_id: str, decision: str, decided_by: str) -> Approval:
        approval = self.get(approval_id)
        if approval is None:
            raise NotFoundError(f"approval {approval_id}")
        if approval.status != "PENDING":
            raise ValueError(f"approval {approval_id} is {approval.status}, not PENDING")
        status = self._DECISION_STATUS.get(decision.lower())
        if status is None:
            raise ValueError(f"unknown decision {decision!r}")
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE approvals SET status = ?, decision = ?, decided_by = ?, decided_at = ?"
                " WHERE id = ?",
                (status, decision.lower(), decided_by, now_iso(), approval_id),
            )
        return self.get(approval_id)  # type: ignore[return-value]

    @staticmethod
    def _row_to_approval(row: sqlite3.Row) -> Approval:
        return Approval(
            id=row["id"], action=row["action"], status=row["status"], agent=row["agent"],
            risk=row["risk"], requested_at=row["requested_at"], decided_at=row["decided_at"],
            decision=row["decision"], decided_by=row["decided_by"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )


# ---------------------------------------------------------------- Knowledge (SPEC-003/010)
class KnowledgeRepository:
    """Documents + chunks + FTS + graph tables (graph engine itself is SPEC-013)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert_document(
        self, uri: str, title: str, doc_type: str, source: str, content_hash: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, bool, bool]:
        """Return (document_id, changed, created).
        changed=False when content_hash matches; created=True when the document is new.
        Atomic under BEGIN IMMEDIATE (single-writer SQLite, ADR-0002).
        """
        conn = self._db.conn_checked
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id, content_hash FROM documents WHERE uri = ?", (uri,)
            ).fetchone()
            if existing is not None and existing["content_hash"] == content_hash:
                return existing["id"], False, False
            doc_id = new_id()
            now = now_iso()
            if existing is not None:
                doc_id = existing["id"]
                conn.execute(
                    "UPDATE documents SET title = ?, doc_type = ?, source = ?, content_hash = ?,"
                    " metadata = ?, updated_at = ? WHERE id = ?",
                    (title, doc_type, source, content_hash,
                     json.dumps(metadata or {}, ensure_ascii=False), now, doc_id),
                )
                conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
            else:
                conn.execute(
                    "INSERT INTO documents (id, workspace_id, uri, title, doc_type, source,"
                    " content_hash, metadata, created_at, updated_at)"
                    " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (doc_id, uri, title, doc_type, source, content_hash,
                     json.dumps(metadata or {}, ensure_ascii=False), now, now),
                )
        return doc_id, True, existing is None

    def add_chunks(self, document_id: str, chunks: list[dict[str, Any]]) -> int:
        """chunks: [{'chunk_id', 'chunk_index', 'heading', 'position', 'content', 'metadata'}]"""
        conn = self._db.conn_checked
        with conn:
            for c in chunks:
                conn.execute(
                    "INSERT INTO document_chunks (chunk_id, document_id, chunk_index, heading,"
                    " position, content, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (c["chunk_id"], document_id, c["chunk_index"], c.get("heading"),
                     c["position"], c["content"],
                     json.dumps(c.get("metadata") or {}, ensure_ascii=False)),
                )
        return len(chunks)

    def search(self, query: str, limit: int = 10, doc_type: str | None = None) -> list[dict[str, Any]]:
        conn = self._db.conn_checked
        fts_query = _fts_query(query)
        sql = (
            "SELECT c.chunk_id, c.chunk_index, c.heading, c.position, d.uri, d.title, d.doc_type,"
            " snippet(document_chunks_fts, 0, '[', ']', '…', 12) AS snip,"
            " bm25(document_chunks_fts) AS rank"
            " FROM document_chunks_fts f"
            " JOIN document_chunks c ON c.id = f.rowid"
            " JOIN documents d ON d.id = c.document_id"
            " WHERE document_chunks_fts MATCH ?"
        )
        params: list[Any] = [fts_query]
        if doc_type:
            sql += " AND d.doc_type = ?"
            params.append(doc_type)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        return [
            {
                "rank": float(r["rank"]), "chunk_id": r["chunk_id"],
                "chunk_index": r["chunk_index"], "heading": r["heading"],
                "position": r["position"], "uri": r["uri"], "title": r["title"],
                "doc_type": r["doc_type"], "snippet": r["snip"],
            }
            for r in rows
        ]

    def upsert_node(self, node_type: str, name: str, canonical_name: str | None = None,
                    description: str | None = None, confidence: float | None = None,
                    source: str | None = None, metadata: dict[str, Any] | None = None) -> str:
        conn = self._db.conn_checked
        existing = conn.execute(
            "SELECT id FROM knowledge_nodes WHERE node_type = ? AND name = ?",
            (node_type, name),
        ).fetchone()
        now = now_iso()
        with conn:
            if existing is not None:
                conn.execute(
                    "UPDATE knowledge_nodes SET canonical_name = ?, description = ?,"
                    " confidence = ?, source = ?, metadata = ?, updated_at = ? WHERE id = ?",
                    (canonical_name, description, confidence, source,
                     json.dumps(metadata or {}, ensure_ascii=False), now, existing["id"]),
                )
                return existing["id"]
            node_id = new_id()
            conn.execute(
                "INSERT INTO knowledge_nodes (id, workspace_id, node_type, name, canonical_name,"
                " description, metadata, confidence, source, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (node_id, node_type, name, canonical_name, description,
                 json.dumps(metadata or {}, ensure_ascii=False), confidence, source, now, now),
            )
            return node_id

    def upsert_edge(self, source_node: str, target_node: str, relationship: str,
                    weight: float | None = None, confidence: float | None = None,
                    source: str | None = None) -> str:
        conn = self._db.conn_checked
        existing = conn.execute(
            "SELECT id FROM knowledge_edges WHERE source_node = ? AND target_node = ?"
            " AND relationship = ?",
            (source_node, target_node, relationship),
        ).fetchone()
        now = now_iso()
        with conn:
            if existing is not None:
                conn.execute(
                    "UPDATE knowledge_edges SET weight = ?, confidence = ?, source = ?"
                    " WHERE id = ?",
                    (weight, confidence, source, existing["id"]),
                )
                return existing["id"]
            edge_id = new_id()
            conn.execute(
                "INSERT INTO knowledge_edges (id, workspace_id, source_node, target_node,"
                " relationship, weight, confidence, source, created_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?)",
                (edge_id, source_node, target_node, relationship, weight, confidence, source, now),
            )
            return edge_id

    def doc_ids_for_chunks(self, chunk_ids: list[str]) -> dict[str, str]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = self._db.conn_checked.execute(
            f"SELECT chunk_id, document_id FROM document_chunks"
            f" WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        return {r["chunk_id"]: r["document_id"] for r in rows}

    def chunks_for_document(self, document_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT chunk_id, chunk_index, heading, position, content, metadata"
            " FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
            (document_id,),
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["metadata"] = json.loads(item["metadata"] or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
            result.append(item)
        return result

    def list_documents(self, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT id, uri, title, doc_type, source, created_at FROM documents"
            " ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_nodes(self, node_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        q = "SELECT * FROM knowledge_nodes"
        params: list[Any] = []
        if node_type:
            q += " WHERE node_type = ?"
            params.append(node_type)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def list_edges(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM knowledge_edges ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------- Embeddings (SPEC-011)
class EmbeddingRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def by_content_hash(self, content_hash: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM embeddings WHERE content_hash = ?", (content_hash,)
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert(self, chunk_id: str, document_id: str, content_hash: str,
               vector: list[float], provider: str, model: str | None = None) -> str:
        conn = self._db.conn_checked
        row_id = new_id()
        now = now_iso()
        with conn:
            conn.execute(
                "INSERT INTO embeddings (id, workspace_id, content_hash, document_id, chunk_id,"
                " dimension, vector, provider, model, created_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(chunk_id) DO UPDATE SET vector = excluded.vector,"
                " content_hash = excluded.content_hash, provider = excluded.provider,"
                " model = excluded.model",
                (row_id, content_hash, document_id, chunk_id, len(vector),
                 json.dumps(vector), provider, model, now),
            )
        return row_id

    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._db.conn_checked:
            cur = self._db.conn_checked.execute(
                f"DELETE FROM embeddings WHERE chunk_id IN ({placeholders})", chunk_ids
            )
            return cur.rowcount

    def delete_by_document(self, document_id: str) -> int:
        with self._db.conn_checked:
            cur = self._db.conn_checked.execute(
                "DELETE FROM embeddings WHERE document_id = ?", (document_id,)
            )
            return cur.rowcount

    def candidates(self, doc_type: str | None = None, limit: int = 2000) -> list[dict[str, Any]]:
        q = (
            "SELECT e.chunk_id, e.vector, e.content_hash, c.content, c.heading, d.uri, d.title, d.doc_type"
            " FROM embeddings e"
            " JOIN document_chunks c ON c.chunk_id = e.chunk_id"
            " JOIN documents d ON d.id = e.document_id"
        )
        params: list[Any] = []
        if doc_type:
            q += " WHERE d.doc_type = ?"
            params.append(doc_type)
        q += f" LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["vector"] = json.loads(item["vector"])
            except (json.JSONDecodeError, TypeError):
                item["vector"] = []
            result.append(item)
        return result


# ---------------------------------------------------------------- Memory (SPEC-014)
class MemoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def put(self, scope: str, key: str, value: str, source: str | None = None,
            confidence: float | None = None, sensitivity: str = "INTERNAL",
            retention_seconds: int | None = None) -> None:
        now = now_iso()
        expires = None
        if retention_seconds is not None:
            from datetime import datetime, timedelta, timezone

            expires = (datetime.now(timezone.utc) + timedelta(seconds=retention_seconds)).isoformat()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO memories (id, workspace_id, scope, key, value, source, confidence,"
                " sensitivity, retention_seconds, created_at, expires_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(scope, key) DO UPDATE SET value = excluded.value,"
                " source = excluded.source, confidence = excluded.confidence,"
                " sensitivity = excluded.sensitivity, retention_seconds = excluded.retention_seconds,"
                " expires_at = excluded.expires_at",
                (new_id(), scope, key, value, source, confidence, sensitivity,
                 retention_seconds, now, expires),
            )

    def get(self, scope: str, key: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM memories WHERE scope = ? AND key = ?", (scope, key)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] and row["expires_at"] <= now_iso():
            self.delete(scope, key)
            return None
        return dict(row)

    def list(self, scope: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        q = "SELECT * FROM memories"
        params: list[Any] = []
        if scope:
            q += " WHERE scope = ?"
            params.append(scope)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        now = now_iso()
        live = []
        for r in rows:
            if r["expires_at"] and r["expires_at"] <= now:
                continue
            live.append(dict(r))
        return live

    def delete(self, scope: str, key: str) -> bool:
        with self._db.conn_checked:
            cur = self._db.conn_checked.execute(
                "DELETE FROM memories WHERE scope = ? AND key = ?", (scope, key)
            )
            return cur.rowcount > 0


# ---------------------------------------------------------------- Research (SPEC-021)
class ResearchRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, research_id: str, question: str, status: str, plan: list[str],
               sources: list[dict[str, Any]], extractions: list[dict[str, Any]],
               synthesis: str, insights: list[dict[str, Any]],
               opportunities: list[dict[str, Any]], trace_id: str | None = None,
               model: str | None = None, provider: str | None = None,
               mock: bool = True) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO research (id, workspace_id, question, status, plan, sources,"
                " extractions, synthesis, insights, opportunities, trace_id, model,"
                " provider, mock, created_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (research_id, question, status, json.dumps(plan, ensure_ascii=False),
                 json.dumps(sources, ensure_ascii=False),
                 json.dumps(extractions, ensure_ascii=False), synthesis,
                 json.dumps(insights, ensure_ascii=False),
                 json.dumps(opportunities, ensure_ascii=False), trace_id, model,
                 provider, 1 if mock else 0, now_iso()),
            )

    def get(self, research_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM research WHERE id = ?", (research_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        for field in ("plan", "sources", "extractions", "insights", "opportunities"):
            try:
                item[field] = json.loads(item[field] or "[]")
            except json.JSONDecodeError:
                item[field] = []
        return item

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT id, question, status, created_at FROM research"
            " ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def insert_insight(self, insight_id: str, research_id: str, insight_type: str,
                       content: str, evidence: str | None, confidence: float | None,
                       source: str | None) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO insights (id, workspace_id, research_id, insight_type, content,"
                " evidence, confidence, source, created_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?)",
                (insight_id, research_id, insight_type, content, evidence, confidence,
                 source, now_iso()),
            )

    def list_insights(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM insights ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------- Growth (SPEC-034)
class OpportunityRepository:
    """Prioritized opportunities with explainable ICE/RICE breakdowns."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, source: str, problem: str, source_ref: str | None = None,
               audience: str | None = None, evidence: str | None = None,
               impact: float | None = None, confidence: float | None = None,
               effort: float | None = None, reach: float | None = None,
               strategic_alignment: float | None = None,
               recommended_action: str | None = None, score: float | None = None,
               score_method: str | None = None,
               breakdown: dict[str, Any] | None = None) -> str:
        opportunity_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO opportunities (id, workspace_id, source, source_ref, problem,"
                " audience, evidence, impact, confidence, effort, reach,"
                " strategic_alignment, recommended_action, score, score_method, breakdown,"
                " status, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)",
                (opportunity_id, source, source_ref, problem, audience, evidence, impact,
                 confidence, effort, reach, strategic_alignment, recommended_action, score,
                 score_method, json.dumps(breakdown or {}, ensure_ascii=False), now, now),
            )
        return opportunity_id

    def update_components(self, opportunity_id: str, **components: Any) -> None:
        """Update scoring components (impact/confidence/effort/reach/alignment).

        Component changes invalidate the cached score: the stored score/breakdown
        is cleared so the next scoring pass recomputes (SPEC-034 R3).
        """
        allowed = {"impact", "confidence", "effort", "reach", "strategic_alignment"}
        updates = {k: v for k, v in components.items() if k in allowed and v is not None}
        if not updates:
            return
        sets = [f"{k} = ?" for k in updates]
        sets.append("score = NULL")
        sets.append("score_method = NULL")
        sets.append("breakdown = '{}'")
        sets.append("updated_at = ?")
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                f"UPDATE opportunities SET {', '.join(sets)} WHERE id = ?",
                [*updates.values(), now_iso(), opportunity_id],
            )

    def get(self, opportunity_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["breakdown"] = json.loads(item["breakdown"] or "{}")
        except json.JSONDecodeError:
            item["breakdown"] = {}
        return item

    def list(self, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        q = "SELECT * FROM opportunities"
        params: list[Any] = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY score DESC NULLS LAST, created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["breakdown"] = json.loads(item["breakdown"] or "{}")
            except json.JSONDecodeError:
                item["breakdown"] = {}
            result.append(item)
        return result

    def update_status(self, opportunity_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE opportunities SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), opportunity_id),
            )

    def update_score(self, opportunity_id: str, score: float, method: str,
                     breakdown: dict[str, Any]) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE opportunities SET score = ?, score_method = ?, breakdown = ?,"
                " updated_at = ? WHERE id = ?",
                (score, method, json.dumps(breakdown, ensure_ascii=False),
                 now_iso(), opportunity_id),
            )


class ExperimentRepository:
    """Experiments with hypothesis, metrics, guardrails, decision and learning."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, opportunity_id: str, problem: str, hypothesis: str,
               primary_metric: str, evidence: str | None = None, change: str | None = None,
               audience: str | None = None, secondary_metrics: list[str] | None = None,
               guardrails: list[str] | None = None, expected_impact: float | None = None,
               confidence: float | None = None, effort: float | None = None) -> str:
        experiment_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO experiments (id, workspace_id, opportunity_id, problem,"
                " evidence, hypothesis, change, audience, primary_metric,"
                " secondary_metrics, guardrails, expected_impact, confidence, effort,"
                " status, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPOSED', ?, ?)",
                (experiment_id, opportunity_id, problem, evidence, hypothesis, change,
                 audience, primary_metric, json.dumps(secondary_metrics or [],
                                                      ensure_ascii=False),
                 json.dumps(guardrails or [], ensure_ascii=False), expected_impact,
                 confidence, effort, now, now),
            )
        return experiment_id

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        for key in ("secondary_metrics", "guardrails"):
            try:
                item[key] = json.loads(item[key] or "[]")
            except json.JSONDecodeError:
                item[key] = []
        return item

    def list(self, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        q = "SELECT * FROM experiments"
        params: list[Any] = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def update_status(self, experiment_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE experiments SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), experiment_id),
            )

    def complete(self, experiment_id: str, result: str, analysis: str,
                 decision: str, learning: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE experiments SET status = 'COMPLETED', result = ?, analysis = ?,"
                " decision = ?, learning = ?, updated_at = ? WHERE id = ?",
                (result, analysis, decision, learning, now_iso(), experiment_id),
            )


# ---------------------------------------------------------------- SEO (SPEC-023)
class SeoRepository:
    """Persisted SEO audits + issues (history across runs, SPEC-023)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_audit(self, scope: str, summary: dict[str, Any]) -> str:
        audit_id = new_id()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO seo_audits (id, workspace_id, scope, summary, run_at)"
                " VALUES (?, 'default', ?, ?, ?)",
                (audit_id, scope, json.dumps(summary, ensure_ascii=False), now_iso()),
            )
        return audit_id

    def insert_issue(self, audit_id: str, severity: str, category: str,
                     target: str | None, title: str, detail: str | None,
                     recommendation: str | None) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO seo_issues (id, workspace_id, audit_id, severity, category,"
                " target, title, detail, recommendation, run_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), audit_id, severity, category, target, title, detail,
                 recommendation, now_iso()),
            )

    def list_issues(self, severity: str | None = None, limit: int = 200
                    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM seo_issues"
        params: list[Any] = []
        if severity:
            q += " WHERE severity = ?"
            params.append(severity)
        q += " ORDER BY run_at DESC, severity LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def last_audit_summary(self) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT summary FROM seo_audits ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        if row is None or not row["summary"]:
            return None
        try:
            return json.loads(row["summary"])
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------- Content (SPEC-022)
class ContentRepository:
    """Content objects + versioned snapshots (auditability, SPEC-022)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, content_type: str, title: str, slug: str, topic: str | None = None,
               audience: str | None = None, persona: str | None = None,
               funnel_stage: str | None = None, objective: str | None = None,
               keywords: list[str] | None = None, brief: str | None = None,
               sources: list[str] | None = None, body: str | None = None,
               cta: str | None = None, score: float | None = None,
               score_breakdown: dict[str, Any] | None = None,
               mock: bool = True, source_workflow: str | None = None) -> str:
        content_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO content (id, workspace_id, content_type, status, title, slug,"
                " topic, audience, persona, funnel_stage, objective, keywords, brief,"
                " sources, body, cta, score, score_breakdown, mock, source_workflow,"
                " created_at, updated_at, version)"
                " VALUES (?, 'default', ?, 'IDEA', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                " ?, ?, ?, ?, 1)",
                (content_id, content_type, title, slug, topic, audience, persona,
                 funnel_stage, objective, json.dumps(keywords or [], ensure_ascii=False),
                 brief, json.dumps(sources or [], ensure_ascii=False), body, cta, score,
                 json.dumps(score_breakdown or {}, ensure_ascii=False),
                 1 if mock else 0, source_workflow, now, now),
            )
        return content_id

    def get(self, content_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM content WHERE id = ?", (content_id,)
        ).fetchone()
        if row is None:
            return None
        return self._decode(dict(row))

    def by_slug(self, slug: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM content WHERE slug = ?", (slug,)
        ).fetchone()
        return self._decode(dict(row)) if row else None

    def list(self, status: str | None = None, content_type: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
        q = "SELECT * FROM content"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if content_type:
            clauses.append("content_type = ?")
            params.append(content_type)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def update(self, content_id: str, **fields: Any) -> None:
        allowed = {"status", "title", "topic", "audience", "persona", "funnel_stage",
                   "objective", "keywords", "brief", "sources", "body", "cta", "score",
                   "score_breakdown", "mock", "source_workflow"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        set_clauses = []
        params: list[Any] = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            params.append(self._encode_value(key, value))
        set_clauses.append("updated_at = ?")
        params.append(now_iso())
        params.append(content_id)
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                f"UPDATE content SET {', '.join(set_clauses)} WHERE id = ?", params
            )

    def snapshot_version(self, content_id: str) -> int:
        """Copy current state to content_versions, bump version. Returns new version."""
        item = self.get(content_id)
        if item is None:
            raise NotFoundError(f"content {content_id}")
        conn = self._db.conn_checked
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT version FROM content WHERE id = ?", (content_id,)
            ).fetchone()
            version = int(row["version"])
            conn.execute(
                "INSERT INTO content_versions (id, workspace_id, content_id, version,"
                " status, title, body, brief, created_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), content_id, version, item["status"], item["title"],
                 item["body"], item["brief"], now_iso()),
            )
            conn.execute(
                "UPDATE content SET version = ?, updated_at = ? WHERE id = ?",
                (version + 1, now_iso(), content_id),
            )
        return version + 1

    def versions(self, content_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM content_versions WHERE content_id = ?"
            " ORDER BY version DESC LIMIT ?", (content_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _decode(item: dict[str, Any]) -> dict[str, Any]:
        for key in ("keywords", "sources", "assets", "distribution", "metrics",
                    "score_breakdown"):
            try:
                item[key] = json.loads(item[key] or "[]") if key != "score_breakdown" \
                    else json.loads(item[key] or "{}")
            except (json.JSONDecodeError, TypeError):
                item[key] = {} if key == "score_breakdown" else []
        item["mock"] = bool(item.get("mock"))
        return item

    @staticmethod
    def _encode_value(key: str, value: Any) -> Any:
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if key == "mock":
            return 1 if value else 0
        return value


# ---------------------------------------------------------------- Factory
class BlogRepository:
    """Published blog posts (SPEC-024): deterministic markdown + front matter,
    gated by human approval. One publish per post (idempotent by design).
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, content_id: str | None, slug: str, title: str, body: str,
               front_matter: dict[str, Any], adapter: str = "local",
               publish_dir: str | None = None) -> str:
        post_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO blog_posts (id, workspace_id, content_id, slug, title, body,"
                " front_matter, status, adapter, publish_dir, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?)",
                (post_id, content_id, slug, title, body,
                 json.dumps(front_matter, ensure_ascii=False), adapter, publish_dir,
                 now, now),
            )
        return post_id

    def get(self, post_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM blog_posts WHERE id = ?", (post_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["front_matter"] = json.loads(item["front_matter"] or "{}")
        except json.JSONDecodeError:
            item["front_matter"] = {}
        return item

    def by_slug(self, slug: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM blog_posts WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["front_matter"] = json.loads(item["front_matter"] or "{}")
        except json.JSONDecodeError:
            item["front_matter"] = {}
        return item

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        q = "SELECT * FROM blog_posts"
        params: list[Any] = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["front_matter"] = json.loads(item["front_matter"] or "{}")
            except json.JSONDecodeError:
                item["front_matter"] = {}
            items.append(item)
        return items

    def update(self, post_id: str, **fields: Any) -> None:
        allowed = {"status", "adapter", "publish_dir", "published_path",
                   "published_url", "published_at", "approval_id"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        set_clauses = [f"{k} = ?" for k in updates]
        set_clauses.append("updated_at = ?")
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                f"UPDATE blog_posts SET {', '.join(set_clauses)} WHERE id = ?",
                [*updates.values(), now_iso(), post_id],
            )


class AnalyticsRepository:
    """Metric snapshots + deterministic insights (SPEC-035). History preserved."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_snapshot(self, metrics: dict[str, Any],
                        summary: dict[str, Any]) -> str:
        snapshot_id = new_id()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO metric_snapshots (id, workspace_id, run_at, metrics, summary)"
                " VALUES (?, 'default', ?, ?, ?)",
                (snapshot_id, now_iso(),
                 json.dumps(metrics, ensure_ascii=False),
                 json.dumps(summary, ensure_ascii=False)),
            )
        return snapshot_id

    def insert_insight(self, snapshot_id: str, insight_type: str, content: str,
                       severity: str, evidence: str | None,
                       confidence: float | None) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO analytics_insights (id, workspace_id, snapshot_id,"
                " insight_type, severity, content, evidence, confidence, created_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), snapshot_id, insight_type, severity, content, evidence,
                 confidence, now_iso()),
            )

    def latest_snapshot(self) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM metric_snapshots ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        for key in ("metrics", "summary"):
            try:
                item[key] = json.loads(item[key] or "{}")
            except json.JSONDecodeError:
                item[key] = {}
        return item

    def list_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT id, run_at FROM metric_snapshots ORDER BY run_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def insights(self, insight_type: str | None = None, limit: int = 100
                 ) -> list[dict[str, Any]]:
        q = "SELECT * FROM analytics_insights"
        params: list[Any] = []
        if insight_type:
            q += " WHERE insight_type = ?"
            params.append(insight_type)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [dict(r) for r in rows]


class SocialPostRepository:
    """Social posts (SPEC-025): deterministic per-channel posts gated by
    human approval. One post per (content_id, channel); FAILED posts may be
    re-prepared.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, content_id: str | None, slug: str, channel: str, text: str,
               hashtags: list[str], adapter: str = "local",
               publish_dir: str | None = None,
               scheduled_at: str | None = None) -> str:
        post_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO social_posts (id, workspace_id, content_id, slug, channel,"
                " text, hashtags, status, adapter, publish_dir, scheduled_at, created_at,"
                " updated_at) VALUES (?, 'default', ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?)",
                (post_id, content_id, slug, channel, text,
                 json.dumps(hashtags, ensure_ascii=False), adapter, publish_dir,
                 scheduled_at, now, now),
            )
        return post_id

    def get(self, post_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM social_posts WHERE id = ?", (post_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["hashtags"] = json.loads(item["hashtags"] or "[]")
        except json.JSONDecodeError:
            item["hashtags"] = []
        return item

    def by_content_channel(self, content_id: str, channel: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM social_posts WHERE content_id = ? AND channel = ?",
            (content_id, channel),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["hashtags"] = json.loads(item["hashtags"] or "[]")
        except json.JSONDecodeError:
            item["hashtags"] = []
        return item

    def list(self, status: str | None = None, channel: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
        q = "SELECT * FROM social_posts"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if channel:
            clauses.append("channel = ?")
            params.append(channel)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["hashtags"] = json.loads(item["hashtags"] or "[]")
            except json.JSONDecodeError:
                item["hashtags"] = []
            items.append(item)
        return items

    def due(self, now: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """SCHEDULED posts whose scheduled_at has arrived (SPEC-025 R4)."""
        rows = self._db.conn_checked.execute(
            "SELECT * FROM social_posts WHERE status = 'SCHEDULED'"
            " AND scheduled_at IS NOT NULL AND scheduled_at <= ?"
            " ORDER BY scheduled_at ASC LIMIT ?",
            (now or now_iso(), limit),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["hashtags"] = json.loads(item["hashtags"] or "[]")
            except json.JSONDecodeError:
                item["hashtags"] = []
            items.append(item)
        return items

    def update(self, post_id: str, **fields: Any) -> None:
        allowed = {"status", "slug", "scheduled_at", "adapter", "publish_dir",
                   "text", "hashtags", "published_path", "published_url",
                   "published_at", "approval_id"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        set_clauses = [f"{k} = ?" for k in updates]
        params: list[Any] = []
        for key, value in updates.items():
            params.append(json.dumps(value, ensure_ascii=False)
                          if key == "hashtags" else value)
        set_clauses.append("updated_at = ?")
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                f"UPDATE social_posts SET {', '.join(set_clauses)} WHERE id = ?",
                [*params, now_iso(), post_id],
            )


class CampaignRepository:
    """Campaigns with content/social/experiment linking (SPEC-040)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        name: str,
        slug: str,
        campaign_type: str,
        hypothesis: str | None = None,
        objective: str | None = None,
        audience: str | None = None,
        budget: float | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        target_metrics: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        campaign_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO campaigns (id, workspace_id, name, slug, campaign_type,"
                " hypothesis, objective, audience, budget, start_date, end_date,"
                " target_metrics, tags, status, total_spend, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PLANNED', 0, ?, ?)",
                (
                    campaign_id, name, slug, campaign_type, hypothesis, objective,
                    audience, budget, start_date, end_date,
                    json.dumps(target_metrics or {}, ensure_ascii=False),
                    json.dumps(tags or [], ensure_ascii=False), now, now,
                ),
            )
        return campaign_id

    def get(self, campaign_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if row is None:
            return None
        return self._decode(dict(row))

    def by_slug(self, slug: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM campaigns WHERE slug = ?", (slug,)
        ).fetchone()
        return self._decode(dict(row)) if row else None

    def list(
        self,
        status: str | None = None,
        campaign_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM campaigns"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if campaign_type:
            clauses.append("campaign_type = ?")
            params.append(campaign_type)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def update_status(self, campaign_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE campaigns SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), campaign_id),
            )

    def update(self, campaign_id: str, **fields: Any) -> None:
        allowed = {
            "name", "hypothesis", "objective", "audience", "budget",
            "start_date", "end_date", "target_metrics", "tags",
            "result", "cancel_reason",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        set_clauses = []
        params: list[Any] = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            if key in ("target_metrics", "tags"):
                params.append(json.dumps(value, ensure_ascii=False))
            else:
                params.append(value)
        set_clauses.append("updated_at = ?")
        params.append(now_iso())
        params.append(campaign_id)
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                f"UPDATE campaigns SET {', '.join(set_clauses)} WHERE id = ?", params
            )

    def add_content(self, campaign_id: str, content_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT OR IGNORE INTO campaign_content"
                " (campaign_id, content_id, created_at) VALUES (?, ?, ?)",
                (campaign_id, content_id, now_iso()),
            )

    def remove_content(self, campaign_id: str, content_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "DELETE FROM campaign_content WHERE campaign_id = ? AND content_id = ?",
                (campaign_id, content_id),
            )

    def list_content(self, campaign_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT c.* FROM content c"
            " JOIN campaign_content cc ON c.id = cc.content_id"
            " WHERE cc.campaign_id = ? ORDER BY cc.created_at",
            (campaign_id,),
        ).fetchall()
        return [ContentRepository._decode(dict(r)) for r in rows]

    def add_social_post(self, campaign_id: str, post_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT OR IGNORE INTO campaign_social"
                " (campaign_id, post_id, created_at) VALUES (?, ?, ?)",
                (campaign_id, post_id, now_iso()),
            )

    def remove_social_post(self, campaign_id: str, post_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "DELETE FROM campaign_social WHERE campaign_id = ? AND post_id = ?",
                (campaign_id, post_id),
            )

    def list_social_posts(self, campaign_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT sp.* FROM social_posts sp"
            " JOIN campaign_social cs ON sp.id = cs.post_id"
            " WHERE cs.campaign_id = ? ORDER BY cs.created_at",
            (campaign_id,),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["hashtags"] = json.loads(item["hashtags"] or "[]")
            except json.JSONDecodeError:
                item["hashtags"] = []
            items.append(item)
        return items

    def add_experiment(self, campaign_id: str, experiment_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT OR IGNORE INTO campaign_experiments"
                " (campaign_id, experiment_id, created_at) VALUES (?, ?, ?)",
                (campaign_id, experiment_id, now_iso()),
            )

    def remove_experiment(self, campaign_id: str, experiment_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "DELETE FROM campaign_experiments WHERE campaign_id = ? AND experiment_id = ?",
                (campaign_id, experiment_id),
            )

    def list_experiments(self, campaign_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT e.* FROM experiments e"
            " JOIN campaign_experiments ce ON e.id = ce.experiment_id"
            " WHERE ce.campaign_id = ? ORDER BY ce.created_at",
            (campaign_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def record_metric(
        self,
        campaign_id: str,
        metric_name: str,
        value: float,
        source: str | None = None,
    ) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO campaign_metrics"
                " (id, campaign_id, metric_name, value, source, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (new_id(), campaign_id, metric_name, value, source, now_iso()),
            )

    def get_metrics(self, campaign_id: str) -> dict[str, Any]:
        rows = self._db.conn_checked.execute(
            "SELECT metric_name, value, source, recorded_at FROM campaign_metrics"
            " WHERE campaign_id = ? ORDER BY recorded_at",
            (campaign_id,),
        ).fetchall()
        metrics: dict[str, Any] = {}
        for row in rows:
            name = row["metric_name"]
            if name not in metrics:
                metrics[name] = {"values": [], "latest": 0, "sum": 0, "count": 0}
            metrics[name]["values"].append({
                "value": row["value"],
                "source": row["source"],
                "recorded_at": row["recorded_at"],
            })
            metrics[name]["latest"] = row["value"]
            metrics[name]["sum"] += row["value"]
            metrics[name]["count"] += 1
        return metrics

    def record_spend(
        self, campaign_id: str, amount: float, description: str | None = None
    ) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO campaign_spends"
                " (id, campaign_id, amount, description, recorded_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (new_id(), campaign_id, amount, description, now_iso()),
            )
            self._db.conn_checked.execute(
                "UPDATE campaigns SET total_spend = total_spend + ?, updated_at = ?"
                " WHERE id = ?",
                (amount, now_iso(), campaign_id),
            )

    def list_spends(self, campaign_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM campaign_spends WHERE campaign_id = ? ORDER BY recorded_at",
            (campaign_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _decode(item: dict[str, Any]) -> dict[str, Any]:
        for key in ("target_metrics", "tags"):
            try:
                item[key] = json.loads(item[key] or "{}" if key == "target_metrics" else "[]")
            except json.JSONDecodeError:
                item[key] = {} if key == "target_metrics" else []
        return item


class LeadRepository:
    """Leads with scoring, qualification, and interactions (SPEC-026/027/028)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        email: str,
        name: str | None = None,
        company: str | None = None,
        source: str = "manual",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        lead_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO leads (id, workspace_id, email, name, company, source,"
                " tags, metadata, status, interaction_count, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, 'CAPTURED', 0, ?, ?)",
                (
                    lead_id, email, name, company, source,
                    json.dumps(tags or [], ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False), now, now,
                ),
            )
        return lead_id

    def get(self, lead_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if row is None:
            return None
        return self._decode(dict(row))

    def by_email(self, email: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM leads WHERE email = ?", (email.lower(),)
        ).fetchone()
        return self._decode(dict(row)) if row else None

    def list(
        self,
        status: str | None = None,
        source: str | None = None,
        company: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM leads"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if company:
            clauses.append("company = ?")
            params.append(company)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def update_status(self, lead_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), lead_id),
            )

    def update_qualification(self, lead_id: str, method: str, criteria: dict[str, Any]) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE leads SET qualification_method = ?, qualification_criteria = ?,"
                " qualified_at = ?, updated_at = ? WHERE id = ?",
                (method, json.dumps(criteria, ensure_ascii=False), now_iso(), now_iso(), lead_id),
            )

    def disqualify(self, lead_id: str, reason: str, notes: str | None) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE leads SET disqualification_reason = ?, disqualification_notes = ?,"
                " disqualified_at = ?, updated_at = ? WHERE id = ?",
                (reason, notes, now_iso(), now_iso(), lead_id),
            )

    def update_score(self, lead_id: str, score: float, breakdown: dict[str, Any]) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE leads SET score = ?, score_breakdown = ?, updated_at = ? WHERE id = ?",
                (score, json.dumps(breakdown, ensure_ascii=False), now_iso(), lead_id),
            )

    def record_interaction(
        self,
        lead_id: str,
        interaction_type: str,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO lead_interactions"
                " (id, lead_id, interaction_type, summary, metadata, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (new_id(), lead_id, interaction_type, summary,
                 json.dumps(metadata or {}, ensure_ascii=False), now_iso()),
            )

    def increment_interactions(self, lead_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE leads SET interaction_count = interaction_count + 1,"
                " updated_at = ? WHERE id = ?",
                (now_iso(), lead_id),
            )

    def list_interactions(self, lead_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM lead_interactions WHERE lead_id = ? ORDER BY created_at",
            (lead_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _decode(item: dict[str, Any]) -> dict[str, Any]:
        for key in ("tags", "metadata", "score_breakdown", "qualification_criteria"):
            try:
                item[key] = json.loads(item[key] or "{}" if key in ("metadata", "score_breakdown", "qualification_criteria") else "[]")
            except json.JSONDecodeError:
                item[key] = {} if key in ("metadata", "score_breakdown", "qualification_criteria") else []
        return item


class CRMRepository:
    """CRM deals, stages, and activities (SPEC-029)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- stages ------------------------------------------------------------
    def create_stage(
        self, name: str, order: int, probability: float = 0,
        is_won: bool = False, is_lost: bool = False,
    ) -> str:
        stage_id = new_id()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO crm_deal_stages"
                " (id, workspace_id, name, \"order\", probability, is_won, is_lost)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?)",
                (stage_id, name, order, probability, 1 if is_won else 0, 1 if is_lost else 0),
            )
        return stage_id

    def list_stages(self) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM crm_deal_stages ORDER BY \"order\""
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- deals -------------------------------------------------------------
    def create_deal(
        self, name: str, lead_id: str | None = None, value: float | None = None,
        currency: str = "BRL", expected_close_date: str | None = None,
        owner_id: str | None = None, tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        deal_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO crm_deals"
                " (id, workspace_id, lead_id, name, value, currency, stage, probability,"
                " expected_close_date, owner_id, tags, metadata, status, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, 'PROSPECTING', 0.1, ?, ?, ?, ?, 'OPEN', ?, ?)",
                (
                    deal_id, lead_id, name, value, currency, expected_close_date,
                    owner_id, json.dumps(tags or [], ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False), now, now,
                ),
            )
        return deal_id

    def get_deal(self, deal_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM crm_deals WHERE id = ?", (deal_id,)
        ).fetchone()
        if row is None:
            return None
        return self._decode_deal(dict(row))

    def list_deals(
        self, status: str | None = None, stage: str | None = None,
        owner_id: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM crm_deals"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if stage:
            clauses.append("stage = ?")
            params.append(stage)
        if owner_id:
            clauses.append("owner_id = ?")
            params.append(owner_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [self._decode_deal(dict(r)) for r in rows]

    def update_deal_stage(self, deal_id: str, stage: str, probability: float) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE crm_deals SET stage = ?, probability = ?, updated_at = ? WHERE id = ?",
                (stage, probability, now_iso(), deal_id),
            )

    def update_deal_status(self, deal_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE crm_deals SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), deal_id),
            )

    def update_deal(self, deal_id: str, **fields: Any) -> None:
        allowed = {"name", "value", "currency", "expected_close_date",
                   "owner_id", "tags", "metadata"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        set_clauses = []
        params: list[Any] = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            if key in ("tags", "metadata"):
                params.append(json.dumps(value, ensure_ascii=False))
            else:
                params.append(value)
        set_clauses.append("updated_at = ?")
        params.append(now_iso())
        params.append(deal_id)
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                f"UPDATE crm_deals SET {', '.join(set_clauses)} WHERE id = ?", params
            )

    # ---- activities --------------------------------------------------------
    def create_activity(
        self, activity_type: str, deal_id: str | None = None,
        lead_id: str | None = None, subject: str | None = None,
        description: str | None = None, due_date: str | None = None,
        owner_id: str | None = None,
    ) -> str:
        activity_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO crm_activities"
                " (id, workspace_id, deal_id, lead_id, activity_type, subject,"
                " description, due_date, owner_id, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (activity_id, deal_id, lead_id, activity_type, subject,
                 description, due_date, owner_id, now, now),
            )
        return activity_id

    def get_activity(self, activity_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM crm_activities WHERE id = ?", (activity_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_activities(
        self, deal_id: str | None = None, lead_id: str | None = None,
        activity_type: str | None = None, completed: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM crm_activities"
        clauses: list[str] = []
        params: list[Any] = []
        if deal_id:
            clauses.append("deal_id = ?")
            params.append(deal_id)
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        if activity_type:
            clauses.append("activity_type = ?")
            params.append(activity_type)
        if completed is not None:
            clauses.append("completed = ?")
            params.append(1 if completed else 0)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def complete_activity(self, activity_id: str, notes: str | None = None) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE crm_activities SET completed = 1, updated_at = ? WHERE id = ?",
                (now_iso(), activity_id),
            )

    @staticmethod
    def _decode_deal(item: dict[str, Any]) -> dict[str, Any]:
        for key in ("tags", "metadata"):
            try:
                item[key] = json.loads(item[key] or "[]")
            except json.JSONDecodeError:
                item[key] = []
        return item


class MeetingRepository:
    """Meeting scheduling (SPEC-031/032)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self, title: str, scheduled_at: str, lead_id: str | None = None,
        deal_id: str | None = None, meeting_type: str = "discovery",
        duration_minutes: int = 30, timezone: str = "UTC",
        location: str | None = None, meeting_url: str | None = None,
        description: str | None = None, owner_id: str | None = None,
        attendees: list[str] | None = None,
    ) -> str:
        meeting_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO meetings"
                " (id, workspace_id, lead_id, deal_id, title, description,"
                " meeting_type, scheduled_at, duration_minutes, timezone,"
                " location, meeting_url, status, owner_id, attendees,"
                " created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SCHEDULED', ?, ?, ?, ?)",
                (
                    meeting_id, lead_id, deal_id, title, description, meeting_type,
                    scheduled_at, duration_minutes, timezone, location, meeting_url,
                    owner_id, json.dumps(attendees or [], ensure_ascii=False), now, now,
                ),
            )
        return meeting_id

    def get(self, meeting_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["attendees"] = json.loads(item["attendees"] or "[]")
        except json.JSONDecodeError:
            item["attendees"] = []
        return item

    def list(
        self, status: str | None = None, lead_id: str | None = None,
        deal_id: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM meetings"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        if deal_id:
            clauses.append("deal_id = ?")
            params.append(deal_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY scheduled_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["attendees"] = json.loads(item["attendees"] or "[]")
            except json.JSONDecodeError:
                item["attendees"] = []
            items.append(item)
        return items

    def update_status(self, meeting_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE meetings SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), meeting_id),
            )

    def complete(self, meeting_id: str, notes: str | None = None, outcome: str | None = None) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE meetings SET status = 'COMPLETED', notes = ?, outcome = ?,"
                " updated_at = ? WHERE id = ?",
                (notes, outcome, now_iso(), meeting_id),
            )

    def upcoming(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get upcoming meetings (SCHEDULED and future)."""
        now = now_iso()
        rows = self._db.conn_checked.execute(
            "SELECT * FROM meetings WHERE status = 'SCHEDULED'"
            " AND scheduled_at >= ? ORDER BY scheduled_at ASC LIMIT ?",
            (now, limit),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["attendees"] = json.loads(item["attendees"] or "[]")
            except json.JSONDecodeError:
                item["attendees"] = []
            items.append(item)
        return items


class EmailRepository:
    """Email sequences and nurture (SPEC-033)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_sequence(
        self, name: str, trigger_event: str, description: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> str:
        seq_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO email_sequences"
                " (id, workspace_id, name, description, trigger_event,"
                " status, steps, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, 'DRAFT', ?, ?, ?)",
                (
                    seq_id, name, description, trigger_event,
                    json.dumps(steps or [], ensure_ascii=False), now, now,
                ),
            )
        return seq_id

    def get_sequence(self, sequence_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM email_sequences WHERE id = ?", (sequence_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["steps"] = json.loads(item["steps"] or "[]")
        except json.JSONDecodeError:
            item["steps"] = []
        return item

    def list_sequences(self, status: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM email_sequences"
        params: list[Any] = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC"
        rows = self._db.conn_checked.execute(q, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["steps"] = json.loads(item["steps"] or "[]")
            except json.JSONDecodeError:
                item["steps"] = []
            items.append(item)
        return items

    def enroll_lead(self, sequence_id: str, lead_id: str) -> str:
        enrollment_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO email_enrollments"
                " (id, workspace_id, sequence_id, lead_id, status, current_step,"
                " enrolled_at, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, 'ACTIVE', 0, ?, ?, ?)",
                (enrollment_id, sequence_id, lead_id, now, now, now),
            )
        return enrollment_id

    def list_enrollments(self, sequence_id: str | None = None, lead_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM email_enrollments"
        clauses: list[str] = []
        params: list[Any] = []
        if sequence_id:
            clauses.append("sequence_id = ?")
            params.append(sequence_id)
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY enrolled_at DESC"
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def add_to_suppression(self, email: str, reason: str, source: str | None = None) -> str:
        suppression_id = new_id()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT OR IGNORE INTO email_suppression_list"
                " (id, workspace_id, email, reason, source, created_at)"
                " VALUES (?, 'default', ?, ?, ?, ?)",
                (suppression_id, email.lower(), reason, source, now_iso()),
            )
        return suppression_id

    def is_suppressed(self, email: str) -> bool:
        row = self._db.conn_checked.execute(
            "SELECT id FROM email_suppression_list WHERE email = ?",
            (email.lower(),),
        ).fetchone()
        return row is not None

    def list_suppressions(self) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM email_suppression_list ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_sequence_status(self, sequence_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE email_sequences SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), sequence_id),
            )

    def complete_enrollment(self, enrollment_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE email_enrollments SET status = 'COMPLETED', completed_at = ?,"
                " updated_at = ? WHERE id = ?",
                (now_iso(), now_iso(), enrollment_id),
            )

    def update_enrollment_step(self, enrollment_id: str, step: int) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE email_enrollments SET current_step = ?, updated_at = ? WHERE id = ?",
                (step, now_iso(), enrollment_id),
            )


class AcademyRepository:
    """Academy content, learner progress, and certifications (SPEC-036)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self, title: str, slug: str, content_type: str,
        description: str | None = None, difficulty: str = "beginner",
        duration_minutes: int | None = None, parent_id: str | None = None,
        prerequisites: list[str] | None = None, tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        content_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO academy_content"
                " (id, workspace_id, title, slug, content_type, description,"
                " difficulty, duration_minutes, parent_id, prerequisites,"
                " tags, metadata, status, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)",
                (
                    content_id, title, slug, content_type, description,
                    difficulty, duration_minutes, parent_id,
                    json.dumps(prerequisites or [], ensure_ascii=False),
                    json.dumps(tags or [], ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False), now, now,
                ),
            )
        return content_id

    def get(self, content_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM academy_content WHERE id = ?", (content_id,)
        ).fetchone()
        if row is None:
            return None
        return self._decode(dict(row))

    def by_slug(self, slug: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM academy_content WHERE slug = ?", (slug,)
        ).fetchone()
        return self._decode(dict(row)) if row else None

    def list(
        self, content_type: str | None = None, status: str | None = None,
        difficulty: str | None = None, parent_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM academy_content"
        clauses: list[str] = []
        params: list[Any] = []
        if content_type:
            clauses.append("content_type = ?")
            params.append(content_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if difficulty:
            clauses.append("difficulty = ?")
            params.append(difficulty)
        if parent_id:
            clauses.append("parent_id = ?")
            params.append(parent_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def update_status(self, content_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE academy_content SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), content_id),
            )

    def enroll_learner(self, content_id: str, learner_id: str) -> str:
        enrollment_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO academy_enrollments"
                " (id, content_id, learner_id, status, progress_pct,"
                " enrolled_at, created_at, updated_at)"
                " VALUES (?, ?, ?, 'ENROLLED', 0, ?, ?, ?)",
                (enrollment_id, content_id, learner_id, now, now, now),
            )
        return enrollment_id

    def get_enrollment(self, enrollment_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM academy_enrollments WHERE id = ?", (enrollment_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_enrollment_by_learner(self, content_id: str, learner_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM academy_enrollments WHERE content_id = ? AND learner_id = ?",
            (content_id, learner_id),
        ).fetchone()
        return dict(row) if row else None

    def update_progress(self, enrollment_id: str, progress_pct: float, notes: str | None) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE academy_enrollments SET progress_pct = ?, notes = ?,"
                " updated_at = ? WHERE id = ?",
                (progress_pct, notes, now_iso(), enrollment_id),
            )

    def update_enrollment_status(self, enrollment_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE academy_enrollments SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), enrollment_id),
            )

    def list_learners(self, content_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM academy_enrollments WHERE content_id = ?"
            " ORDER BY enrolled_at",
            (content_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_learner_enrollments(self, learner_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT e.*, c.title, c.content_type FROM academy_enrollments e"
            " JOIN academy_content c ON e.content_id = c.id"
            " WHERE e.learner_id = ? ORDER BY e.enrolled_at",
            (learner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def issue_certification(
        self, content_id: str, learner_id: str, assessment_score: float | None
    ) -> str:
        cert_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO academy_certifications"
                " (id, content_id, learner_id, assessment_score, issued_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (cert_id, content_id, learner_id, assessment_score, now),
            )
        return cert_id

    def get_certification(self, cert_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM academy_certifications WHERE id = ?", (cert_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_certifications(self, learner_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM academy_certifications"
        params: list[Any] = []
        if learner_id:
            q += " WHERE learner_id = ?"
            params.append(learner_id)
        q += " ORDER BY issued_at DESC"
        rows = self._db.conn_checked.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _decode(item: dict[str, Any]) -> dict[str, Any]:
        for key in ("prerequisites", "tags", "metadata"):
            try:
                item[key] = json.loads(item[key] or "[]" if key != "metadata" else "{}")
            except json.JSONDecodeError:
                item[key] = {} if key == "metadata" else []
        return item


class CommunityRepository:
    """Community members, threads, and replies (SPEC-037)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- members -----------------------------------------------------------
    def add_member(
        self, name: str, external_id: str | None = None, email: str | None = None,
        platform: str = "internal", role: str = "member",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        member_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO community_members"
                " (id, workspace_id, external_id, name, email, platform,"
                " role, joined_at, metadata)"
                " VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?)",
                (
                    member_id, external_id, name, email, platform, role, now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
        return member_id

    def get_member(self, member_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM community_members WHERE id = ?", (member_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["metadata"] = json.loads(item["metadata"] or "{}")
        except json.JSONDecodeError:
            item["metadata"] = {}
        return item

    def list_members(
        self, platform: str | None = None, role: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM community_members"
        clauses: list[str] = []
        params: list[Any] = []
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if role:
            clauses.append("role = ?")
            params.append(role)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY joined_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item["metadata"] or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
            items.append(item)
        return items

    def update_activity(self, member_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE community_members SET last_active_at = ? WHERE id = ?",
                (now_iso(), member_id),
            )

    # ---- threads -----------------------------------------------------------
    def create_thread(
        self, channel: str, title: str, author_id: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        thread_id = new_id()
        now = now_iso()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO community_threads"
                " (id, workspace_id, channel, title, author_id, tags,"
                " status, reply_count, created_at, updated_at)"
                " VALUES (?, 'default', ?, ?, ?, ?, 'open', 0, ?, ?)",
                (
                    thread_id, channel, title, author_id,
                    json.dumps(tags or [], ensure_ascii=False), now, now,
                ),
            )
        return thread_id

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM community_threads WHERE id = ?", (thread_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["tags"] = json.loads(item["tags"] or "[]")
        except json.JSONDecodeError:
            item["tags"] = []
        return item

    def list_threads(
        self, channel: str | None = None, status: str | None = None,
        author_id: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM community_threads"
        clauses: list[str] = []
        params: list[Any] = []
        if channel:
            clauses.append("channel = ?")
            params.append(channel)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if author_id:
            clauses.append("author_id = ?")
            params.append(author_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn_checked.execute(q, params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["tags"] = json.loads(item["tags"] or "[]")
            except json.JSONDecodeError:
                item["tags"] = []
            items.append(item)
        return items

    def update_thread_status(self, thread_id: str, status: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE community_threads SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), thread_id),
            )

    def increment_reply_count(self, thread_id: str) -> None:
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "UPDATE community_threads SET reply_count = reply_count + 1,"
                " last_reply_at = ?, updated_at = ? WHERE id = ?",
                (now_iso(), now_iso(), thread_id),
            )

    # ---- replies -----------------------------------------------------------
    def add_reply(
        self, thread_id: str, author_id: str, content: str, is_answer: bool = False,
    ) -> str:
        reply_id = new_id()
        with self._db.conn_checked:
            self._db.conn_checked.execute(
                "INSERT INTO community_replies"
                " (id, thread_id, author_id, content, is_answer, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (reply_id, thread_id, author_id, content, 1 if is_answer else 0, now_iso()),
            )
        return reply_id

    def get_reply(self, reply_id: str) -> dict[str, Any] | None:
        row = self._db.conn_checked.execute(
            "SELECT * FROM community_replies WHERE id = ?", (reply_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_replies(self, thread_id: str) -> list[dict[str, Any]]:
        rows = self._db.conn_checked.execute(
            "SELECT * FROM community_replies WHERE thread_id = ?"
            " ORDER BY created_at",
            (thread_id,),
        ).fetchall()
        return [dict(r) for r in rows]


class RepoFactory:
    """Single access point to repositories for a given Database (SPEC-003 R3.1)."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.runs = RunRepository(db)
        self.events = EventRepository(db)
        self.jobs = JobRepository(db)
        self.approvals = ApprovalRepository(db)
        self.knowledge = KnowledgeRepository(db)
        self.embeddings = EmbeddingRepository(db)
        self.memories = MemoryRepository(db)
        self.research = ResearchRepository(db)
        self.content = ContentRepository(db)
        self.seo = SeoRepository(db)
        self.opportunities = OpportunityRepository(db)
        self.experiments = ExperimentRepository(db)
        self.blog = BlogRepository(db)
        self.social = SocialPostRepository(db)
        self.analytics = AnalyticsRepository(db)
        self.campaigns = CampaignRepository(db)
        self.leads = LeadRepository(db)
        self.crm = CRMRepository(db)
        self.meetings = MeetingRepository(db)
        self.email = EmailRepository(db)
        self.academy = AcademyRepository(db)
        self.community = CommunityRepository(db)


def _fts_query(query: str) -> str:
    """Turn a free-text query into a safe FTS5 query: quoted, prefixed terms."""
    words = [w for w in query.replace('"', " ").split() if w]
    if not words:
        return '""'
    return " ".join(f'"{w}"*' for w in words[:16]) or '""'


def slugify_node_name(name: str) -> str:
    """Canonical node names are slugs (SPEC-027 style deterministic naming)."""
    return slugify(name)
