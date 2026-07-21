-- AI Tutor Agent — full idempotent schema
-- Run via: psql -U ai_tutor -d ai_tutor -f schema.sql
-- All statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS so safe to re-run.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Enum types ────────────────────────────────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE content_type_enum AS ENUM ('pdf','docx','mp4','mp3','wav','url','text');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE document_status_enum AS ENUM ('active','retired','processing','failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE kb_approval_status_enum AS ENUM ('draft','pending_review','approved','rejected','clarification_requested');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── Core user tables ─────────────────────────────────────────────────────────
-- approval_status stored as TEXT (avoids enum dependency for simpler deployment)

CREATE TABLE IF NOT EXISTS roles (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name             VARCHAR(50) NOT NULL UNIQUE,
  description      TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email_encrypted      BYTEA NOT NULL DEFAULT '\x00',
  email_hash           VARCHAR(64) NOT NULL UNIQUE,
  full_name_encrypted  BYTEA NOT NULL DEFAULT '\x00',
  keycloak_id          VARCHAR(255) UNIQUE,
  is_active            BOOLEAN NOT NULL DEFAULT true,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved';
CREATE INDEX IF NOT EXISTS ix_users_email_hash       ON users(email_hash);
CREATE INDEX IF NOT EXISTS ix_users_keycloak_id      ON users(keycloak_id);
CREATE INDEX IF NOT EXISTS ix_users_approval_status  ON users(approval_status);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, role_id)
);
CREATE INDEX IF NOT EXISTS ix_user_roles_user_id ON user_roles(user_id);

-- Self-registration table (mock/dev mode)
CREATE TABLE IF NOT EXISTS user_local_auth (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  desired_role  TEXT NOT NULL DEFAULT 'Learner',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_user_local_auth_email ON user_local_auth(email);

-- Course enrollment
CREATE TABLE IF NOT EXISTS enrollments (
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kb_id      UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, kb_id)
);
CREATE INDEX IF NOT EXISTS ix_enrollments_user ON enrollments(user_id);

-- ── Knowledge bases ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_bases (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name             VARCHAR(255) NOT NULL,
  description      TEXT,
  organization_id  VARCHAR(255) NOT NULL DEFAULT 'default',
  is_active        BOOLEAN NOT NULL DEFAULT true,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id);
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved';
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS ai_overview TEXT;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS age_group VARCHAR(50);
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS clarification_message TEXT;
CREATE INDEX IF NOT EXISTS ix_kb_org ON knowledge_bases(organization_id);

-- ── Documents ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  kb_id       UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  title       VARCHAR(500) NOT NULL,
  source_uri  TEXT,
  content_type content_type_enum NOT NULL DEFAULT 'text',
  status      document_status_enum NOT NULL DEFAULT 'processing',
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_text TEXT;
CREATE INDEX IF NOT EXISTS ix_documents_kb_active ON documents(kb_id, status);

-- ── Document chunks ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS document_chunks (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  chunk_text  TEXT NOT NULL,
  vector_id   VARCHAR(255),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_doc_chunks_document ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS ix_doc_chunks_vector   ON document_chunks(vector_id);

-- ── Learner profile ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS local_learner_profiles (
  user_id       VARCHAR(255) PRIMARY KEY,
  kb_id         UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  total_lessons INTEGER NOT NULL DEFAULT 0,
  completed_lessons INTEGER NOT NULL DEFAULT 0,
  last_activity TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Topic progress ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS local_topic_progress (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id     VARCHAR(255) NOT NULL,
  kb_id       UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  topic       VARCHAR(500) NOT NULL,
  is_complete BOOLEAN NOT NULL DEFAULT false,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_local_topic_user_topic ON local_topic_progress(user_id, kb_id, topic);
CREATE INDEX IF NOT EXISTS ix_local_topic_user ON local_topic_progress(user_id);

-- ── Assessments ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS local_assessments (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  kb_id       UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  title       VARCHAR(500) NOT NULL,
  questions   JSONB NOT NULL DEFAULT '[]',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_local_assessments_kb ON local_assessments(kb_id);

-- ── Assessment results ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS local_assessment_results (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       VARCHAR(255) NOT NULL,
  assessment_id UUID NOT NULL REFERENCES local_assessments(id) ON DELETE CASCADE,
  score         NUMERIC(5,2) NOT NULL DEFAULT 0,
  answers       JSONB NOT NULL DEFAULT '{}',
  completed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_local_results_user ON local_assessment_results(user_id);

-- ── Chat history ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_history (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id  VARCHAR(255) NOT NULL,
  user_id     VARCHAR(255) NOT NULL,
  kb_id       UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
  role        VARCHAR(50) NOT NULL,
  content     TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_chat_session ON chat_history(session_id);
CREATE INDEX IF NOT EXISTS ix_chat_user    ON chat_history(user_id);

-- ── Audit log ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id     VARCHAR(255),
  action      VARCHAR(255) NOT NULL,
  resource    VARCHAR(255),
  details     JSONB,
  ip_address  VARCHAR(45),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_audit_user   ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_log(action);

-- ── Confidence scores ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS confidence_scores (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id    VARCHAR(255) NOT NULL,
  query         TEXT NOT NULL,
  score         NUMERIC(4,3) NOT NULL,
  graded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Admin config ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_config (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  config_key  VARCHAR(255) NOT NULL UNIQUE,
  config_value TEXT NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
