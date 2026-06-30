-- Seed: default admin configuration values (global / org='default')
INSERT INTO admin_configurations (organization_id, config_key, config_value, description) VALUES
  ('default', 'confidence_threshold',    '0.6',                           'Minimum confidence score before external search fallback is triggered'),
  ('default', 'max_tokens_per_request',  '2048',                          'Maximum LLM tokens per chat completion request'),
  ('default', 'rag_top_k',              '5',                             'Number of chunks to retrieve per RAG query'),
  ('default', 'data_retention_days',    '365',                           'Days to retain chat messages and user data before purge'),
  ('default', 'external_search_enabled','false',                         'Allow fallback to external web search when internal KB is insufficient'),
  ('default', 'max_file_size_mb',       '50',                            'Maximum allowed file size for content upload in MB'),
  ('default', 'chunk_size_words',       '350',                           'Target words per document chunk'),
  ('default', 'chunk_overlap_words',    '50',                            'Overlap between consecutive document chunks in words')
ON CONFLICT (organization_id, config_key) DO NOTHING;
