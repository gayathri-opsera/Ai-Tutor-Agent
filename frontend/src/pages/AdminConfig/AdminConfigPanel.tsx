import { useEffect, useState } from 'react';

interface Config { key: string; value: unknown; description: string; }

const ADMIN_API = '/api/v1/admin/config';

const DEFAULT_CONFIGS: Config[] = [
  { key: 'confidence_threshold',   value: 0.4,     description: 'Minimum confidence score before showing answer' },
  { key: 'max_rag_chunks',         value: 5,       description: 'Max chunks returned per RAG query' },
  { key: 'session_ttl_minutes',    value: 60,      description: 'Session expiry time in minutes' },
  { key: 'default_model_tier',     value: 'standard', description: 'LLM tier: small | standard | large' },
  { key: 'data_retention_days',    value: 90,      description: 'Days to retain chat history before purge' },
  { key: 'max_file_size_mb',       value: 50,      description: 'Maximum upload file size (MB)' },
  { key: 'chunk_size_words',       value: 350,     description: 'Target words per document chunk' },
  { key: 'chunk_overlap_words',    value: 50,      description: 'Overlap between consecutive chunks' },
  { key: 'external_search_enabled', value: false,  description: 'Allow fallback to external web search' },
];

export function AdminConfigPanel() {
  const [configs, setConfigs]   = useState<Config[]>(DEFAULT_CONFIGS);
  const [editing, setEditing]   = useState<string | null>(null);
  const [draftVal, setDraftVal] = useState('');
  const [saved, setSaved]       = useState<string | null>(null);
  const [error, setError]       = useState('');

  useEffect(() => {
    fetch(`${ADMIN_API}?organization_id=default`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.configs?.length) {
          setConfigs(d.configs.map((c: { key: string; value: unknown; description: string }) => ({
            key: c.key,
            value: c.value,
            description: c.description || DEFAULT_CONFIGS.find(x => x.key === c.key)?.description || '',
          })));
        }
      })
      .catch(() => { /* use defaults */ });
  }, []);

  const handleSave = async (key: string) => {
    let parsedVal: unknown = draftVal;
    try { parsedVal = JSON.parse(draftVal); } catch { /* keep as string */ }

    setConfigs(c => c.map(cfg => cfg.key === key ? { ...cfg, value: parsedVal } : cfg));
    setEditing(null);
    setSaved(key);
    setTimeout(() => setSaved(null), 2500);

    try {
      const res = await fetch(`${ADMIN_API}/${key}?organization_id=default`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: parsedVal }),
      });
      if (!res.ok) setError('Failed to save — check backend logs');
    } catch (e) {
      setError(String(e));
    }
  };

  const displayValue = (v: unknown): string => {
    if (typeof v === 'object' && v !== null) return JSON.stringify(v);
    return String(v ?? '');
  };

  return (
    <div>
      <div className="page-header">
        <div className="container">
          <div className="page-header-row">
            <div>
              <h1>Admin Configuration</h1>
              <p>Global platform settings for the AI Tutor system</p>
            </div>
            <span className="badge badge-success">● Live</span>
          </div>
        </div>
      </div>

      <div className="container" style={{ paddingTop: 32 }}>
        {error && <div className="alert alert-error mb-4">{error}</div>}

        {/* LLM Provider card */}
        <div className="monitor-card mb-6">
          <p className="monitor-card-title">LLM Provider</p>
          <div className="flex items-center gap-3" style={{ padding: '8px 0' }}>
            <span style={{ fontSize: '2rem' }}>🤖</span>
            <div>
              <p className="font-bold">AI Provider (Groq / Llama 3)</p>
              <p className="text-sm text-muted">Configured via environment · RAG-grounded responses</p>
            </div>
            <span className="badge badge-success" style={{ marginLeft: 'auto' }}>Active</span>
          </div>
        </div>

        {/* Config table */}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Configuration Key</th>
                <th>Value</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {configs.map(cfg => (
                <tr key={cfg.key}>
                  <td>
                    <code style={{ background: 'var(--bg)', padding: '2px 6px', borderRadius: 3, fontSize: '0.82rem' }}>
                      {cfg.key}
                    </code>
                  </td>
                  <td>
                    {editing === cfg.key ? (
                      <input
                        className="form-input" style={{ padding: '4px 8px', width: 120 }}
                        value={draftVal} autoFocus
                        onChange={e => setDraftVal(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') handleSave(cfg.key); if (e.key === 'Escape') setEditing(null); }}
                      />
                    ) : (
                      <span className="badge badge-gray">{displayValue(cfg.value)}</span>
                    )}
                  </td>
                  <td className="text-sm text-muted">{cfg.description}</td>
                  <td>
                    {saved === cfg.key ? (
                      <span className="badge badge-success">✓ Saved</span>
                    ) : editing === cfg.key ? (
                      <div className="flex gap-2">
                        <button className="btn btn-brand btn-sm" onClick={() => handleSave(cfg.key)}>Save</button>
                        <button className="btn btn-outline btn-sm" onClick={() => setEditing(null)}>Cancel</button>
                      </div>
                    ) : (
                      <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(cfg.key); setDraftVal(displayValue(cfg.value)); }}>
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
