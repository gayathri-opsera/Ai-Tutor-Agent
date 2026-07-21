-- AI Tutor Agent — full idempotent schema (matches migrations 0001-0014 + enrollments)
-- Run via: psql -U ai_tutor -d ai_tutor -v ON_ERROR_STOP=1 -f schema.sql
-- All statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS — safe to re-run.

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Enum types ────────────────────────────────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE data_classification_enum AS ENUM ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE content_type_enum AS ENUM ('pdf','docx','mp4','mp3','wav','url','text');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE document_status_enum AS ENUM ('uploading','processing','active','error','retired');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
-- 0003: add pending_review value
ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'pending_review';

DO $$ BEGIN
  CREATE TYPE message_role_enum AS ENUM ('user','assistant','system');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE approval_status_enum AS ENUM ('pending','approved','rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE kb_approval_status_enum AS ENUM ('pending_review','approved','rejected','clarification_requested');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── roles (0001) ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roles (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name             VARCHAR(50) NOT NULL UNIQUE,
  description      TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'INTERNAL'
);

-- ── users (0001) ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email_encrypted      BYTEA NOT NULL DEFAULT '\x00',
  email_hash           VARCHAR(64) NOT NULL UNIQUE,
  full_name_encrypted  BYTEA NOT NULL DEFAULT '\x00',
  keycloak_id          VARCHAR(255) UNIQUE,
  is_active            BOOLEAN NOT NULL DEFAULT true,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification  data_classification_enum NOT NULL DEFAULT 'CONFIDENTIAL'
);
-- 0005: approval_status column (TEXT fallback — avoids enum in ALTER TABLE)
ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'pending';
CREATE INDEX IF NOT EXISTS ix_users_email_hash      ON users(email_hash);
CREATE INDEX IF NOT EXISTS ix_users_keycloak_id     ON users(keycloak_id);
CREATE INDEX IF NOT EXISTS ix_users_approval_status ON users(approval_status);

-- ── user_roles (0001) ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_roles (
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'INTERNAL',
  PRIMARY KEY (user_id, role_id)
);
CREATE INDEX IF NOT EXISTS ix_user_roles_user_id ON user_roles(user_id);

-- ── knowledge_bases (0001 + 0004, 0006, 0007) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_bases (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name             VARCHAR(255) NOT NULL,
  description      TEXT,
  organization_id  VARCHAR(255) NOT NULL,
  created_by       UUID REFERENCES users(id),
  is_active        BOOLEAN NOT NULL DEFAULT true,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'INTERNAL'
);
-- 0006 additions
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'pending_review';
-- Correct the default so new rows require explicit approval
ALTER TABLE knowledge_bases ALTER COLUMN approval_status SET DEFAULT 'pending_review';
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS ai_overview TEXT;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS clarification_message TEXT;
-- 0007 additions
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS age_group VARCHAR(20);
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS created_by_keycloak_id VARCHAR(255);
CREATE INDEX IF NOT EXISTS ix_knowledge_bases_org            ON knowledge_bases(organization_id, is_active);
CREATE INDEX IF NOT EXISTS ix_knowledge_bases_approval       ON knowledge_bases(approval_status);
CREATE INDEX IF NOT EXISTS ix_knowledge_bases_created_by_kc  ON knowledge_bases(created_by_keycloak_id);

-- ── documents (0001 + 0004, 0013) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  title             VARCHAR(500) NOT NULL,
  description       TEXT,
  content_type      content_type_enum NOT NULL,
  s3_bucket         VARCHAR(255),
  s3_key            TEXT,
  file_size_bytes   BIGINT,
  status            document_status_enum NOT NULL DEFAULT 'uploading',
  is_active         BOOLEAN NOT NULL DEFAULT true,
  retired_at        TIMESTAMPTZ,
  chunk_count       INTEGER NOT NULL DEFAULT 0,
  uploaded_by       UUID REFERENCES users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'INTERNAL'
);
-- 0013: content_text column
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_text TEXT;
CREATE INDEX IF NOT EXISTS ix_documents_kb_active ON documents(knowledge_base_id, is_active);
CREATE INDEX IF NOT EXISTS ix_documents_status    ON documents(status);

-- ── document_chunks (0001) ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS document_chunks (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  chunk_text  TEXT NOT NULL,
  vector_id   VARCHAR(255),
  page_number INTEGER,
  metadata    JSONB NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'INTERNAL'
);
CREATE INDEX IF NOT EXISTS ix_chunks_document  ON document_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS ix_chunks_vector_id ON document_chunks(vector_id);

-- ── chat_sessions (0001) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  knowledge_base_id UUID REFERENCES knowledge_bases(id),
  title            VARCHAR(500),
  is_active        BOOLEAN NOT NULL DEFAULT true,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'CONFIDENTIAL'
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON chat_sessions(user_id, created_at);

-- ── chat_messages (0001) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id      UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role            message_role_enum NOT NULL,
  content         TEXT NOT NULL,
  sources_json    JSONB NOT NULL DEFAULT '[]',
  confidence_score FLOAT,
  feedback        SMALLINT,
  feedback_at     TIMESTAMPTZ,
  tokens_used     INTEGER,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'CONFIDENTIAL'
);
CREATE INDEX IF NOT EXISTS ix_messages_session_created ON chat_messages(session_id, created_at);

-- ── learner_profiles (0001) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learner_profiles (
  id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id              UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  preferred_difficulty VARCHAR(50) NOT NULL DEFAULT 'beginner',
  notes_encrypted      BYTEA,
  total_sessions       INTEGER NOT NULL DEFAULT 0,
  total_queries        INTEGER NOT NULL DEFAULT 0,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification  data_classification_enum NOT NULL DEFAULT 'RESTRICTED'
);

-- ── learner_topic_progress (0001) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learner_topic_progress (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  learner_profile_id UUID NOT NULL REFERENCES learner_profiles(id) ON DELETE CASCADE,
  knowledge_base_id  UUID REFERENCES knowledge_bases(id),
  topic             VARCHAR(255) NOT NULL,
  status            VARCHAR(50) NOT NULL DEFAULT 'not_started',
  proficiency_score FLOAT NOT NULL DEFAULT 0.0,
  last_activity_at  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'CONFIDENTIAL'
);
CREATE INDEX IF NOT EXISTS ix_topic_progress_learner ON learner_topic_progress(learner_profile_id, knowledge_base_id);

-- ── assessments (0001) ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assessments (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id),
  title             VARCHAR(255) NOT NULL,
  assessment_type   VARCHAR(50) NOT NULL DEFAULT 'pre',
  questions_json    JSONB NOT NULL DEFAULT '[]',
  created_by        UUID REFERENCES users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'INTERNAL'
);

-- ── assessment_results (0001) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assessment_results (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  assessment_id UUID NOT NULL REFERENCES assessments(id),
  user_id       UUID NOT NULL REFERENCES users(id),
  score         FLOAT,
  answers_json  JSONB NOT NULL DEFAULT '{}',
  completed_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'CONFIDENTIAL'
);
CREATE INDEX IF NOT EXISTS ix_results_user_assessment ON assessment_results(user_id, assessment_id);

-- ── admin_configurations (0001) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_configurations (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id VARCHAR(255) NOT NULL,
  config_key      VARCHAR(255) NOT NULL,
  config_value    JSONB NOT NULL,
  description     TEXT,
  updated_by      UUID REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'INTERNAL',
  CONSTRAINT uq_admin_config UNIQUE (organization_id, config_key)
);
CREATE INDEX IF NOT EXISTS ix_admin_config_org ON admin_configurations(organization_id);

-- ── audit_logs (0001) ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  actor_id      VARCHAR(255) NOT NULL,
  actor_role    VARCHAR(100),
  action        VARCHAR(255) NOT NULL,
  resource_type VARCHAR(100),
  resource_id   VARCHAR(255),
  outcome       VARCHAR(50) NOT NULL,
  ip_address    VARCHAR(45),
  metadata      JSONB NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'RESTRICTED'
);
CREATE INDEX IF NOT EXISTS ix_audit_actor_time ON audit_logs(actor_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_action     ON audit_logs(action, created_at);

-- ── content_feedback (0001) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_feedback (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  message_id UUID NOT NULL REFERENCES chat_messages(id),
  user_id    UUID REFERENCES users(id),
  rating     SMALLINT,
  comment    TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_classification data_classification_enum NOT NULL DEFAULT 'CONFIDENTIAL'
);

-- ── Local dev tables (0002) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS local_learner_profiles (
  user_id          TEXT PRIMARY KEY,
  display_name     TEXT NOT NULL DEFAULT '',
  proficiency_level TEXT NOT NULL DEFAULT 'beginner',
  preferences      JSONB NOT NULL DEFAULT '{}',
  total_sessions   INTEGER NOT NULL DEFAULT 0,
  total_queries    INTEGER NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS local_topic_progress (
  id               TEXT PRIMARY KEY,
  user_id          TEXT NOT NULL REFERENCES local_learner_profiles(user_id) ON DELETE CASCADE,
  topic            TEXT NOT NULL,
  knowledge_base_id TEXT,
  status           TEXT NOT NULL DEFAULT 'not_started',
  score            FLOAT NOT NULL DEFAULT 0.0,
  question_count   INTEGER NOT NULL DEFAULT 0,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_local_topic_user       ON local_topic_progress(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_local_topic_user_topic ON local_topic_progress(user_id, topic);

CREATE TABLE IF NOT EXISTS local_assessments (
  id                TEXT PRIMARY KEY,
  knowledge_base_id TEXT NOT NULL DEFAULT '',
  title             TEXT NOT NULL,
  assessment_type   TEXT NOT NULL DEFAULT 'pre',
  questions_json    JSONB NOT NULL DEFAULT '[]',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_local_assessments_kb ON local_assessments(knowledge_base_id);

CREATE TABLE IF NOT EXISTS local_assessment_results (
  id            TEXT PRIMARY KEY,
  assessment_id TEXT NOT NULL REFERENCES local_assessments(id) ON DELETE CASCADE,
  user_id       TEXT NOT NULL,
  score         FLOAT NOT NULL DEFAULT 0.0,
  correct       INTEGER NOT NULL DEFAULT 0,
  total         INTEGER NOT NULL DEFAULT 0,
  answers_json  JSONB NOT NULL DEFAULT '{}',
  submitted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_local_results_user ON local_assessment_results(user_id);

CREATE TABLE IF NOT EXISTS local_admin_config (
  org_id       TEXT NOT NULL,
  config_key   TEXT NOT NULL,
  config_value JSONB NOT NULL DEFAULT 'null',
  description  TEXT NOT NULL DEFAULT '',
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (org_id, config_key)
);
CREATE INDEX IF NOT EXISTS ix_local_admin_config_org ON local_admin_config(org_id);

CREATE TABLE IF NOT EXISTS local_analytics_events (
  id         TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  user_id    TEXT NOT NULL DEFAULT '',
  topic      TEXT NOT NULL DEFAULT '',
  rating     INTEGER,
  metadata   JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_local_analytics_type ON local_analytics_events(event_type);
CREATE INDEX IF NOT EXISTS ix_local_analytics_user ON local_analytics_events(user_id);

-- Seed default admin config (0002)
INSERT INTO local_admin_config (org_id, config_key, config_value, description)
VALUES
  ('default', 'confidence_threshold', '0.4',          'Minimum confidence score to show answer'),
  ('default', 'max_rag_chunks',       '5',             'Max RAG chunks per query'),
  ('default', 'session_ttl_minutes',  '60',            'Session expiry in minutes'),
  ('default', 'default_model_tier',   '"standard"',    'LLM model tier: small | standard | large'),
  ('default', 'data_retention_days',  '90',            'Days to retain chat history')
ON CONFLICT DO NOTHING;

-- ── user_local_auth (0014) ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_local_auth (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  desired_role  TEXT NOT NULL DEFAULT 'Learner',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_user_local_auth_email ON user_local_auth(email);

-- ── enrollments (feature addition) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enrollments (
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kb_id       UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, kb_id)
);
CREATE INDEX IF NOT EXISTS ix_enrollments_user ON enrollments(user_id);
