import { useEffect, useState } from 'react';
import { apiFetch } from '../../config/apiFetch';

interface Config { key: string; value: unknown; description: string; }
interface PendingKB {
  id: string; name: string; description: string;
  age_group: string | null; created_at?: string;
  created_by_keycloak_id?: string | null;
}

const ADMIN_API = '/api/v1/admin/config';
const KB_API    = '/api/v1/knowledge-bases';

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
  const [configs, setConfigs]         = useState<Config[]>(DEFAULT_CONFIGS);
  const [editing, setEditing]         = useState<string | null>(null);
  const [draftVal, setDraftVal]       = useState('');
  const [saved, setSaved]             = useState<string | null>(null);
  const [error, setError]             = useState('');
  const [pendingKBs, setPendingKBs]   = useState<PendingKB[]>([]);
  const [kbAction, setKbAction]       = useState<Record<string, string>>({});
  const [kbMsg, setKbMsg]             = useState<Record<string, string>>({});

  useEffect(() => {
    apiFetch(`${ADMIN_API}?organization_id=default`)
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

    // Load pending courses for approval
    apiFetch(`${KB_API}/admin/pending`)
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setPendingKBs(Array.isArray(d?.items) ? d.items : []))
      .catch(() => {});
  }, []);

  const handleSave = async (key: string) => {
    let parsedVal: unknown = draftVal;
    try { parsedVal = JSON.parse(draftVal); } catch { /* keep as string */ }

    setConfigs(c => c.map(cfg => cfg.key === key ? { ...cfg, value: parsedVal } : cfg));
    setEditing(null);
    setSaved(key);
    setTimeout(() => setSaved(null), 2500);

    try {
      const res = await apiFetch(`${ADMIN_API}/${key}?organization_id=default`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: parsedVal }),
      });
      if (!res.ok) setError('Failed to save — check backend logs');
    } catch (e) {
      setError(String(e));
    }
  };

  const handleKbApproval = async (kb: PendingKB, action: 'approve' | 'reject') => {
    const reason = kbMsg[kb.id] ?? '';
    try {
      const res = await apiFetch(`${KB_API}/${kb.id}/approval`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, reason: reason || null }),
      });
      if (res.ok) {
        setKbAction(prev => ({ ...prev, [kb.id]: action === 'approve' ? '✓ Approved' : '✗ Rejected' }));
        setTimeout(() => setPendingKBs(prev => prev.filter(k => k.id !== kb.id)), 1200);
      } else {
        setError(`Failed to ${action} course`);
      }
    } catch (e) { setError(String(e)); }
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

        {/* ── Pending Course Approvals ─────────────────────────────────── */}
        {pendingKBs.length > 0 && (
          <div className="monitor-card mb-6" style={{ border: '2px solid #f59e0b' }}>
            <p className="monitor-card-title" style={{ color: '#92400e' }}>
              📋 Pending Course Approvals ({pendingKBs.length})
            </p>
            <p style={{ fontSize: '0.82rem', color: '#78350f', marginBottom: 16 }}>
              Review and approve courses before they become visible to learners.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {pendingKBs.map(kb => (
                <div key={kb.id} style={{
                  background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8,
                  padding: '14px 16px', display: 'flex', alignItems: 'flex-start',
                  gap: 16, flexWrap: 'wrap',
                }}>
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <p style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: 2 }}>{kb.name}</p>
                    <p style={{ fontSize: '0.8rem', color: '#6b7280', marginBottom: 4 }}>
                      {kb.description || 'No description'} · Age group: {kb.age_group ?? 'Any'}
                    </p>
                    <input
                      className="form-input"
                      style={{ fontSize: '0.8rem', padding: '4px 10px', marginTop: 4 }}
                      placeholder="Optional reason / feedback for creator…"
                      value={kbMsg[kb.id] ?? ''}
                      onChange={e => setKbMsg(prev => ({ ...prev, [kb.id]: e.target.value }))}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingTop: 4 }}>
                    {kbAction[kb.id] ? (
                      <span className={`badge ${kbAction[kb.id].startsWith('✓') ? 'badge-success' : 'badge-error'}`}>
                        {kbAction[kb.id]}
                      </span>
                    ) : (
                      <>
                        <button className="btn btn-brand btn-sm"
                          onClick={() => handleKbApproval(kb, 'approve')}>
                          ✓ Approve
                        </button>
                        <button className="btn btn-outline btn-sm"
                          style={{ borderColor: '#dc2626', color: '#dc2626' }}
                          onClick={() => handleKbApproval(kb, 'reject')}>
                          ✗ Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {pendingKBs.length === 0 && (
          <div className="monitor-card mb-6" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: '1.5rem' }}>✅</span>
            <div>
              <p style={{ fontWeight: 700, fontSize: '0.9rem' }}>No pending course approvals</p>
              <p style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>All submitted courses have been reviewed.</p>
            </div>
          </div>
        )}

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

