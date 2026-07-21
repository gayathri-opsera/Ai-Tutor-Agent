-- Seed: sample data for local development
-- Clean slate: remove stale seed data in FK-safe order before re-inserting.
DELETE FROM content_feedback  WHERE message_id IN (SELECT id FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003')));
DELETE FROM chat_messages     WHERE session_id IN (SELECT id FROM chat_sessions WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003'));
DELETE FROM chat_sessions     WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003');
DELETE FROM assessment_results WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003');
DELETE FROM learner_profiles  WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003');
DELETE FROM enrollments       WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003');
DELETE FROM user_local_auth   WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003');
DELETE FROM user_roles        WHERE user_id IN ('aaaaaaaa-0001-0000-0000-000000000001','aaaaaaaa-0002-0000-0000-000000000002','aaaaaaaa-0003-0000-0000-000000000003');
-- Also purge any users with the same email_hash that have different auto-generated IDs
DELETE FROM user_roles      WHERE user_id IN (SELECT id FROM users WHERE email_hash IN (encode(digest('admin@ai-tutor.local','sha256'),'hex'), encode(digest('creator@ai-tutor.local','sha256'),'hex'), encode(digest('learner@ai-tutor.local','sha256'),'hex')));
DELETE FROM user_local_auth WHERE user_id IN (SELECT id FROM users WHERE email_hash IN (encode(digest('admin@ai-tutor.local','sha256'),'hex'), encode(digest('creator@ai-tutor.local','sha256'),'hex'), encode(digest('learner@ai-tutor.local','sha256'),'hex')));
DELETE FROM enrollments     WHERE user_id IN (SELECT id FROM users WHERE email_hash IN (encode(digest('admin@ai-tutor.local','sha256'),'hex'), encode(digest('creator@ai-tutor.local','sha256'),'hex'), encode(digest('learner@ai-tutor.local','sha256'),'hex')));
DELETE FROM users           WHERE email_hash IN (encode(digest('admin@ai-tutor.local','sha256'),'hex'), encode(digest('creator@ai-tutor.local','sha256'),'hex'), encode(digest('learner@ai-tutor.local','sha256'),'hex'));

-- Clean seed knowledge bases and dependent data
DELETE FROM document_chunks WHERE document_id IN (SELECT id FROM documents WHERE knowledge_base_id IN ('bbbbbbbb-0001-0000-0000-000000000001','bbbbbbbb-0002-0000-0000-000000000002'));
DELETE FROM documents       WHERE knowledge_base_id IN ('bbbbbbbb-0001-0000-0000-000000000001','bbbbbbbb-0002-0000-0000-000000000002');
DELETE FROM enrollments     WHERE kb_id IN ('bbbbbbbb-0001-0000-0000-000000000001','bbbbbbbb-0002-0000-0000-000000000002');
DELETE FROM knowledge_bases WHERE id IN ('bbbbbbbb-0001-0000-0000-000000000001','bbbbbbbb-0002-0000-0000-000000000002');

-- Users (PII-safe: encrypted fields use placeholder bytes, email_hash is sha256)
INSERT INTO users (id, email_encrypted, email_hash, full_name_encrypted, keycloak_id, is_active)
VALUES
  ('aaaaaaaa-0001-0000-0000-000000000001',
   '\x61646d696e406169', encode(digest('admin@ai-tutor.local',   'sha256'), 'hex'),
   '\x416c69636520416461', 'keycloak-admin-001',   true),
  ('aaaaaaaa-0002-0000-0000-000000000002',
   '\x637265617465',     encode(digest('creator@ai-tutor.local', 'sha256'), 'hex'),
   '\x426f6220437265',   'keycloak-creator-002', true),
  ('aaaaaaaa-0003-0000-0000-000000000003',
   '\x6c6561726e6572',   encode(digest('learner@ai-tutor.local', 'sha256'), 'hex'),
   '\x4361726f6c204c65', 'keycloak-learner-003', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO user_roles (user_id, role_id) VALUES
  ('aaaaaaaa-0001-0000-0000-000000000001', '00000000-0000-0000-0000-000000000003'), -- Admin
  ('aaaaaaaa-0002-0000-0000-000000000002', '00000000-0000-0000-0000-000000000002'), -- Creator
  ('aaaaaaaa-0003-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001')  -- Learner
ON CONFLICT DO NOTHING;

INSERT INTO knowledge_bases (id, name, description, organization_id, created_by, is_active)
VALUES
  ('bbbbbbbb-0001-0000-0000-000000000001',
   'Python Fundamentals',
   'Core Python programming: variables, functions, OOP, and async patterns.',
   'default', 'aaaaaaaa-0002-0000-0000-000000000002', true),
  ('bbbbbbbb-0002-0000-0000-000000000002',
   'Machine Learning Basics',
   'Intro to supervised, unsupervised, and reinforcement learning.',
   'default', 'aaaaaaaa-0002-0000-0000-000000000002', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO documents (id, knowledge_base_id, title, content_type, status, chunk_count)
VALUES
  ('cccccccc-0001-0000-0000-000000000001', 'bbbbbbbb-0001-0000-0000-000000000001',
   'Introduction to Python',    'text', 'active', 2),
  ('cccccccc-0002-0000-0000-000000000002', 'bbbbbbbb-0001-0000-0000-000000000001',
   'Async Programming in Python','text', 'active', 1),
  ('cccccccc-0003-0000-0000-000000000003', 'bbbbbbbb-0002-0000-0000-000000000002',
   'Linear Regression Explained','text', 'active', 1)
ON CONFLICT (id) DO NOTHING;

INSERT INTO document_chunks (id, document_id, chunk_index, chunk_text, vector_id, metadata)
VALUES
  ('dddddddd-0001-0000-0000-000000000001', 'cccccccc-0001-0000-0000-000000000001', 0,
   'Python is a high-level, interpreted language known for readable syntax. It supports procedural, object-oriented, and functional paradigms.',
   'vec-py-001', '{"page": 1}'),
  ('dddddddd-0002-0000-0000-000000000002', 'cccccccc-0001-0000-0000-000000000001', 1,
   'Variables in Python are dynamically typed. Python infers the type at runtime — no declaration needed.',
   'vec-py-002', '{"page": 2}'),
  ('dddddddd-0003-0000-0000-000000000003', 'cccccccc-0002-0000-0000-000000000002', 0,
   'Async programming in Python uses asyncio. The async/await keywords enable non-blocking I/O via an event loop.',
   'vec-py-003', '{"page": 1}'),
  ('dddddddd-0004-0000-0000-000000000004', 'cccccccc-0003-0000-0000-000000000003', 0,
   'Linear regression models the relationship between a dependent and independent variable using a linear equation fitted to observed data.',
   'vec-ml-001', '{"page": 1}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO learner_profiles (id, user_id, preferred_difficulty, total_sessions, total_queries)
VALUES
  ('eeeeeeee-0001-0000-0000-000000000001',
   'aaaaaaaa-0003-0000-0000-000000000003', 'beginner', 1, 2)
ON CONFLICT (id) DO NOTHING;

INSERT INTO chat_sessions (id, user_id, knowledge_base_id, title)
VALUES
  ('ffffffff-0001-0000-0000-000000000001',
   'aaaaaaaa-0003-0000-0000-000000000003',
   'bbbbbbbb-0001-0000-0000-000000000001',
   'Learning Python Basics')
ON CONFLICT (id) DO NOTHING;

INSERT INTO chat_messages (id, session_id, role, content, confidence_score, tokens_used)
VALUES
  ('11111111-0001-0000-0000-000000000001', 'ffffffff-0001-0000-0000-000000000001',
   'user', 'What is Python and why is it popular?', NULL, 8),
  ('11111111-0002-0000-0000-000000000002', 'ffffffff-0001-0000-0000-000000000001',
   'assistant',
   'Python is a high-level interpreted language prized for readable syntax. Widely used in data science, AI/ML, web development, and automation.',
   0.92, 35)
ON CONFLICT (id) DO NOTHING;
