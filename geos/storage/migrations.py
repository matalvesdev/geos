"""GEOS migrations (SPEC-002). Ordered, additive, forward-only in bootstrap.

Each entry: (version, name, sql). Versions must be unique and increasing.
"""

from __future__ import annotations


class MigrationError(Exception):
    """Raised when a migration cannot be applied."""


V1_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  workflow_id TEXT,
  agent TEXT,
  trace_id TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms INTEGER,
  model TEXT,
  tokens INTEGER,
  cost REAL,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_trace ON runs(trace_id);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  trace_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT UNIQUE,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  run_after TEXT,
  last_error TEXT,
  trace_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  uri TEXT NOT NULL UNIQUE,
  title TEXT,
  doc_type TEXT,
  source TEXT,
  content_hash TEXT NOT NULL,
  metadata TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chunk_id TEXT NOT NULL UNIQUE,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  heading TEXT,
  position INTEGER NOT NULL,
  content TEXT NOT NULL,
  metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(document_id);

-- FTS5 over chunk content, external content backed by document_chunks rowid.
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
  content, heading,
  content='document_chunks', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS document_chunks_ai AFTER INSERT ON document_chunks BEGIN
  INSERT INTO document_chunks_fts(rowid, content, heading)
  VALUES (new.id, new.content, coalesce(new.heading, ''));
END;
CREATE TRIGGER IF NOT EXISTS document_chunks_ad AFTER DELETE ON document_chunks BEGIN
  INSERT INTO document_chunks_fts(document_chunks_fts, rowid, content, heading)
  VALUES ('delete', old.id, old.content, coalesce(old.heading, ''));
END;
CREATE TRIGGER IF NOT EXISTS document_chunks_au AFTER UPDATE ON document_chunks BEGIN
  INSERT INTO document_chunks_fts(document_chunks_fts, rowid, content, heading)
  VALUES ('delete', old.id, old.content, coalesce(old.heading, ''));
  INSERT INTO document_chunks_fts(rowid, content, heading)
  VALUES (new.id, new.content, coalesce(new.heading, ''));
END;

CREATE TABLE IF NOT EXISTS knowledge_nodes (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  node_type TEXT NOT NULL,
  name TEXT NOT NULL,
  canonical_name TEXT,
  description TEXT,
  metadata TEXT,
  confidence REAL,
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON knowledge_nodes(node_type);

CREATE TABLE IF NOT EXISTS knowledge_edges (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  source_node TEXT NOT NULL,
  target_node TEXT NOT NULL,
  relationship TEXT NOT NULL,
  weight REAL,
  confidence REAL,
  source TEXT,
  valid_from TEXT,
  valid_to TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON knowledge_edges(source_node);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  action TEXT NOT NULL,
  agent TEXT,
  risk TEXT,
  status TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  decision TEXT,
  decided_by TEXT,
  metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  actor TEXT,
  agent TEXT,
  action TEXT NOT NULL,
  resource TEXT,
  previous_state TEXT,
  new_state TEXT,
  trace_id TEXT,
  approval_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
"""


V2_KNOWLEDGE_PHASE1 = """
CREATE TABLE IF NOT EXISTS embeddings (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  content_hash TEXT NOT NULL,
  document_id TEXT,
  chunk_id TEXT UNIQUE,
  dimension INTEGER NOT NULL,
  vector TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON embeddings(content_hash);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  scope TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  source TEXT,
  confidence REAL,
  sensitivity TEXT NOT NULL DEFAULT 'INTERNAL',
  retention_seconds INTEGER,
  created_at TEXT NOT NULL,
  expires_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_scope_key ON memories(scope, key);

CREATE TABLE IF NOT EXISTS research (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  question TEXT NOT NULL,
  status TEXT NOT NULL,
  plan TEXT,
  sources TEXT,
  extractions TEXT,
  synthesis TEXT,
  insights TEXT,
  opportunities TEXT,
  trace_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_created ON research(created_at);

CREATE TABLE IF NOT EXISTS insights (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  research_id TEXT,
  insight_type TEXT NOT NULL,
  content TEXT NOT NULL,
  evidence TEXT,
  confidence REAL,
  source TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type);
"""


V5_SEO = """
CREATE TABLE IF NOT EXISTS seo_audits (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  scope TEXT NOT NULL,
  summary TEXT,
  run_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seo_audits_run ON seo_audits(run_at);

CREATE TABLE IF NOT EXISTS seo_issues (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  audit_id TEXT REFERENCES seo_audits(id) ON DELETE CASCADE,
  severity TEXT NOT NULL,
  category TEXT NOT NULL,
  target TEXT,
  title TEXT NOT NULL,
  detail TEXT,
  recommendation TEXT,
  run_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seo_issues_severity ON seo_issues(severity);
CREATE INDEX IF NOT EXISTS idx_seo_issues_audit ON seo_issues(audit_id);
"""


V4_MODEL_PROVENANCE = """
-- Additive provenance for LLM-generated synthesis (SPEC-039): model, provider,
-- and mock flag on research rows. Safe ALTERs (no rewrite of existing data).
ALTER TABLE research ADD COLUMN model TEXT;
ALTER TABLE research ADD COLUMN provider TEXT;
ALTER TABLE research ADD COLUMN mock INTEGER NOT NULL DEFAULT 1;
"""


V3_CONTENT_PHASE2 = """
CREATE TABLE IF NOT EXISTS content (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  content_type TEXT NOT NULL,
  status TEXT NOT NULL,
  title TEXT NOT NULL,
  slug TEXT NOT NULL,
  topic TEXT,
  audience TEXT,
  persona TEXT,
  funnel_stage TEXT,
  objective TEXT,
  keywords TEXT,
  brief TEXT,
  sources TEXT,
  body TEXT,
  assets TEXT,
  cta TEXT,
  distribution TEXT,
  metrics TEXT,
  score REAL,
  score_breakdown TEXT,
  mock INTEGER NOT NULL DEFAULT 1,
  source_workflow TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_content_slug ON content(slug);
CREATE INDEX IF NOT EXISTS idx_content_status ON content(status);
CREATE INDEX IF NOT EXISTS idx_content_type ON content(content_type);

CREATE TABLE IF NOT EXISTS content_versions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  content_id TEXT NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  title TEXT,
  body TEXT,
  brief TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_versions_content ON content_versions(content_id);
"""


MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "bootstrap", V1_BOOTSTRAP),
    (2, "knowledge_phase1", V2_KNOWLEDGE_PHASE1),
    (3, "content_phase2", V3_CONTENT_PHASE2),
    (4, "model_provenance", V4_MODEL_PROVENANCE),
    (5, "seo_engine", V5_SEO),
]

MAX_VERSION = max(v for v, _, _ in MIGRATIONS)
