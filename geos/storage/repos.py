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


def _fts_query(query: str) -> str:
    """Turn a free-text query into a safe FTS5 query: quoted, prefixed terms."""
    words = [w for w in query.replace('"', " ").split() if w]
    if not words:
        return '""'
    return " ".join(f'"{w}"*' for w in words[:16]) or '""'


def slugify_node_name(name: str) -> str:
    """Canonical node names are slugs (SPEC-027 style deterministic naming)."""
    return slugify(name)
