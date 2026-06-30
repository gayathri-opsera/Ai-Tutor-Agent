-- Seed: default roles
INSERT INTO roles (id, name, description) VALUES
  ('00000000-0000-0000-0000-000000000001', 'Learner',    'Standard learner — can query knowledge bases and view their own history'),
  ('00000000-0000-0000-0000-000000000002', 'Creator',    'Content creator — can upload and manage content in knowledge bases'),
  ('00000000-0000-0000-0000-000000000003', 'Admin',      'Organization administrator — manages users, configurations, and knowledge bases'),
  ('00000000-0000-0000-0000-000000000004', 'SuperAdmin', 'Platform superadmin — cross-organization access for platform management')
ON CONFLICT (name) DO NOTHING;
