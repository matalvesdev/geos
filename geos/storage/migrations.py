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


V6_OPPORTUNITIES = """
CREATE TABLE IF NOT EXISTS opportunities (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  source TEXT NOT NULL,
  source_ref TEXT,
  problem TEXT NOT NULL,
  audience TEXT,
  evidence TEXT,
  impact REAL,
  confidence REAL,
  effort REAL,
  reach REAL,
  strategic_alignment REAL,
  recommended_action TEXT,
  score REAL,
  score_method TEXT,
  breakdown TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(score);

CREATE TABLE IF NOT EXISTS experiments (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  opportunity_id TEXT REFERENCES opportunities(id),
  problem TEXT NOT NULL,
  evidence TEXT,
  hypothesis TEXT NOT NULL,
  change TEXT,
  audience TEXT,
  primary_metric TEXT NOT NULL,
  secondary_metrics TEXT,
  guardrails TEXT,
  expected_impact REAL,
  confidence REAL,
  effort REAL,
  status TEXT NOT NULL DEFAULT 'PROPOSED',
  result TEXT,
  analysis TEXT,
  decision TEXT,
  learning TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
CREATE INDEX IF NOT EXISTS idx_experiments_opportunity ON experiments(opportunity_id);
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


V9_ANALYTICS = """
CREATE TABLE IF NOT EXISTS metric_snapshots (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  run_at TEXT NOT NULL,
  metrics TEXT NOT NULL,
  summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metric_snapshots_run ON metric_snapshots(run_at);

CREATE TABLE IF NOT EXISTS analytics_insights (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  snapshot_id TEXT REFERENCES metric_snapshots(id) ON DELETE CASCADE,
  insight_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info',
  content TEXT NOT NULL,
  evidence TEXT,
  confidence REAL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analytics_insights_type ON analytics_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_analytics_insights_snapshot ON analytics_insights(snapshot_id);
"""


V8_SOCIAL = """
CREATE TABLE IF NOT EXISTS social_posts (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  content_id TEXT REFERENCES content(id),
  slug TEXT NOT NULL,
  channel TEXT NOT NULL,
  text TEXT NOT NULL,
  hashtags TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  scheduled_at TEXT,
  adapter TEXT NOT NULL DEFAULT 'local',
  publish_dir TEXT,
  published_path TEXT,
  published_url TEXT,
  published_at TEXT,
  approval_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_social_content_channel ON social_posts(content_id, channel);
CREATE INDEX IF NOT EXISTS idx_social_status ON social_posts(status);
CREATE INDEX IF NOT EXISTS idx_social_scheduled ON social_posts(scheduled_at);
"""


V7_BLOG = """
CREATE TABLE IF NOT EXISTS blog_posts (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  content_id TEXT REFERENCES content(id),
  slug TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  front_matter TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  adapter TEXT NOT NULL DEFAULT 'local',
  publish_dir TEXT,
  published_path TEXT,
  published_url TEXT,
  published_at TEXT,
  approval_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_blog_slug ON blog_posts(slug);
CREATE INDEX IF NOT EXISTS idx_blog_status ON blog_posts(status);
CREATE INDEX IF NOT EXISTS idx_blog_content ON blog_posts(content_id);
"""


V10_CAMPAIGNS = """
CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  campaign_type TEXT NOT NULL,
  hypothesis TEXT,
  objective TEXT,
  audience TEXT,
  budget REAL,
  total_spend REAL NOT NULL DEFAULT 0,
  start_date TEXT,
  end_date TEXT,
  target_metrics TEXT NOT NULL DEFAULT '{}',
  tags TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'PLANNED',
  result TEXT,
  cancel_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_campaigns_slug ON campaigns(slug);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_type ON campaigns(campaign_type);

CREATE TABLE IF NOT EXISTS campaign_content (
  campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  content_id TEXT NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY (campaign_id, content_id)
);

CREATE TABLE IF NOT EXISTS campaign_social (
  campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  post_id TEXT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY (campaign_id, post_id)
);

CREATE TABLE IF NOT EXISTS campaign_experiments (
  campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY (campaign_id, experiment_id)
);

CREATE TABLE IF NOT EXISTS campaign_metrics (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  metric_name TEXT NOT NULL,
  value REAL NOT NULL,
  source TEXT,
  recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_campaign_metrics_name ON campaign_metrics(campaign_id, metric_name);

CREATE TABLE IF NOT EXISTS campaign_spends (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  amount REAL NOT NULL,
  description TEXT,
  recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_campaign_spends_campaign ON campaign_spends(campaign_id);
"""


V11_LEADS = """
CREATE TABLE IF NOT EXISTS leads (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  email TEXT NOT NULL,
  name TEXT,
  company TEXT,
  title TEXT,
  phone TEXT,
  website TEXT,
  linkedin_url TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  tags TEXT NOT NULL DEFAULT '[]',
  metadata TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'CAPTURED',
  owner_id TEXT,
  score REAL,
  score_breakdown TEXT,
  interaction_count INTEGER NOT NULL DEFAULT 0,
  qualification_method TEXT,
  qualification_criteria TEXT,
  qualified_at TEXT,
  disqualification_reason TEXT,
  disqualification_notes TEXT,
  disqualified_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(company);

CREATE TABLE IF NOT EXISTS lead_interactions (
  id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  interaction_type TEXT NOT NULL,
  summary TEXT,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lead_interactions_lead ON lead_interactions(lead_id);

CREATE TABLE IF NOT EXISTS lead_score_history (
  id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  score REAL NOT NULL,
  breakdown TEXT NOT NULL,
  computed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lead_score_history_lead ON lead_score_history(lead_id);
"""

V12_CRM = """
CREATE TABLE IF NOT EXISTS crm_deals (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  lead_id TEXT REFERENCES leads(id),
  name TEXT NOT NULL,
  value REAL,
  currency TEXT NOT NULL DEFAULT 'BRL',
  stage TEXT NOT NULL DEFAULT 'PROSPECTING',
  probability REAL DEFAULT 0,
  expected_close_date TEXT,
  actual_close_date TEXT,
  owner_id TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  metadata TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'OPEN',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_deals_status ON crm_deals(status);
CREATE INDEX IF NOT EXISTS idx_crm_deals_stage ON crm_deals(stage);
CREATE INDEX IF NOT EXISTS idx_crm_deals_lead ON crm_deals(lead_id);

CREATE TABLE IF NOT EXISTS crm_deal_stages (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  name TEXT NOT NULL,
  "order" INTEGER NOT NULL,
  probability REAL DEFAULT 0,
  is_won BOOLEAN DEFAULT 0,
  is_lost BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS crm_activities (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  deal_id TEXT REFERENCES crm_deals(id) ON DELETE CASCADE,
  lead_id TEXT REFERENCES leads(id) ON DELETE CASCADE,
  activity_type TEXT NOT NULL,
  subject TEXT,
  description TEXT,
  due_date TEXT,
  completed BOOLEAN DEFAULT 0,
  owner_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_activities_deal ON crm_activities(deal_id);
CREATE INDEX IF NOT EXISTS idx_crm_activities_lead ON crm_activities(lead_id);
"""

V13_MEETINGS = """
CREATE TABLE IF NOT EXISTS meetings (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  lead_id TEXT REFERENCES leads(id),
  deal_id TEXT REFERENCES crm_deals(id),
  title TEXT NOT NULL,
  description TEXT,
  meeting_type TEXT NOT NULL DEFAULT 'discovery',
  scheduled_at TEXT NOT NULL,
  duration_minutes INTEGER DEFAULT 30,
  timezone TEXT DEFAULT 'UTC',
  location TEXT,
  meeting_url TEXT,
  external_id TEXT,
  status TEXT NOT NULL DEFAULT 'SCHEDULED',
  notes TEXT,
  outcome TEXT,
  owner_id TEXT,
  attendees TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);
CREATE INDEX IF NOT EXISTS idx_meetings_scheduled ON meetings(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_meetings_lead ON meetings(lead_id);
CREATE INDEX IF NOT EXISTS idx_meetings_deal ON meetings(deal_id);
"""

V14_EMAIL_NURTURE = """
CREATE TABLE IF NOT EXISTS email_sequences (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  name TEXT NOT NULL,
  description TEXT,
  trigger_event TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  steps TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_sequences_status ON email_sequences(status);

CREATE TABLE IF NOT EXISTS email_enrollments (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  sequence_id TEXT NOT NULL REFERENCES email_sequences(id) ON DELETE CASCADE,
  lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  current_step INTEGER DEFAULT 0,
  enrolled_at TEXT NOT NULL,
  completed_at TEXT,
  unsubscribed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_enrollments_seq_lead ON email_enrollments(sequence_id, lead_id);

CREATE TABLE IF NOT EXISTS email_suppression_list (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  email TEXT NOT NULL,
  reason TEXT NOT NULL,
  source TEXT,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_suppression_email ON email_suppression_list(email);
"""


V15_ACADEMY = """
CREATE TABLE IF NOT EXISTS academy_content (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  title TEXT NOT NULL,
  slug TEXT NOT NULL,
  content_type TEXT NOT NULL,
  description TEXT,
  difficulty TEXT NOT NULL DEFAULT 'beginner',
  duration_minutes INTEGER,
  parent_id TEXT REFERENCES academy_content(id),
  prerequisites TEXT NOT NULL DEFAULT '[]',
  tags TEXT NOT NULL DEFAULT '[]',
  metadata TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'DRAFT',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_academy_content_slug ON academy_content(slug);
CREATE INDEX IF NOT EXISTS idx_academy_content_type ON academy_content(content_type);
CREATE INDEX IF NOT EXISTS idx_academy_content_status ON academy_content(status);
CREATE INDEX IF NOT EXISTS idx_academy_content_parent ON academy_content(parent_id);

CREATE TABLE IF NOT EXISTS academy_enrollments (
  id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL REFERENCES academy_content(id) ON DELETE CASCADE,
  learner_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ENROLLED',
  progress_pct REAL DEFAULT 0,
  notes TEXT,
  enrolled_at TEXT NOT NULL,
  completed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_academy_enrollments_learner ON academy_enrollments(content_id, learner_id);
CREATE INDEX IF NOT EXISTS idx_academy_enrollments_status ON academy_enrollments(status);

CREATE TABLE IF NOT EXISTS academy_certifications (
  id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL REFERENCES academy_content(id),
  learner_id TEXT NOT NULL,
  assessment_score REAL,
  issued_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_academy_certifications_learner ON academy_certifications(learner_id);
"""

V16_COMMUNITY = """
CREATE TABLE IF NOT EXISTS community_members (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  external_id TEXT,
  name TEXT NOT NULL,
  email TEXT,
  platform TEXT NOT NULL DEFAULT 'internal',
  role TEXT NOT NULL DEFAULT 'member',
  joined_at TEXT NOT NULL,
  last_active_at TEXT,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_community_members_external ON community_members(external_id);
CREATE INDEX IF NOT EXISTS idx_community_members_platform ON community_members(platform);

CREATE TABLE IF NOT EXISTS community_threads (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL DEFAULT 'default',
  channel TEXT NOT NULL,
  title TEXT NOT NULL,
  author_id TEXT REFERENCES community_members(id),
  tags TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'open',
  reply_count INTEGER DEFAULT 0,
  last_reply_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_community_threads_channel ON community_threads(channel);
CREATE INDEX IF NOT EXISTS idx_community_threads_status ON community_threads(status);

CREATE TABLE IF NOT EXISTS community_replies (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES community_threads(id) ON DELETE CASCADE,
  author_id TEXT REFERENCES community_members(id),
  content TEXT NOT NULL,
  is_answer BOOLEAN DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_community_replies_thread ON community_replies(thread_id);
"""


MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "bootstrap", V1_BOOTSTRAP),
    (2, "knowledge_phase1", V2_KNOWLEDGE_PHASE1),
    (3, "content_phase2", V3_CONTENT_PHASE2),
    (4, "model_provenance", V4_MODEL_PROVENANCE),
    (5, "seo_engine", V5_SEO),
    (6, "opportunities_experiments", V6_OPPORTUNITIES),
    (7, "blog_publisher", V7_BLOG),
    (8, "social_scheduler", V8_SOCIAL),
    (9, "analytics", V9_ANALYTICS),
    (10, "campaigns", V10_CAMPAIGNS),
    (11, "leads", V11_LEADS),
    (12, "crm", V12_CRM),
    (13, "meetings", V13_MEETINGS),
    (14, "email_nurture", V14_EMAIL_NURTURE),
    (15, "academy", V15_ACADEMY),
    (16, "community", V16_COMMUNITY),
]

MAX_VERSION = max(v for v, _, _ in MIGRATIONS)
