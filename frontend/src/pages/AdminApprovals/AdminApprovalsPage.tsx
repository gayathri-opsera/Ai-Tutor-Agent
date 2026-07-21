import { useState, useEffect } from 'react';
import { apiFetch } from '../../config/apiFetch';

const KB_API = '/api/v1/knowledge-bases';

interface PendingKB {
  id: string;
  name: string;
  description: string;
  organization_id: string;
  approval_status: string;
  created_at?: string;
}

type ActionState = 'idle' | 'loading' | 'approved' | 'rejected';

export function AdminApprovalsPage() {
  const [pending, setPending]     = useState<PendingKB[]>([]);
  const [loading, setLoading]     = useState(true);
  const [reasons, setReasons]     = useState<Record<string, string>>({});
  const [actions, setActions]     = useState<Record<string, ActionState>>({});
  const [error, setError]         = useState('');

  useEffect(() => {
    apiFetch(`${KB_API}/admin/pending`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(d => { setPending(Array.isArray(d?.items) ? d.items : []); setLoading(false); })
      .catch(() => { setPending([]); setLoading(false); });
  }, []);

  const handle = async (kb: PendingKB, action: 'approve' | 'reject') => {
    setActions(prev => ({ ...prev, [kb.id]: 'loading' }));
    setError('');
    try {
      const res = await apiFetch(`${KB_API}/${kb.id}/approval`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, reason: reasons[kb.id] || null }),
      });
      if (res.ok) {
        setActions(prev => ({ ...prev, [kb.id]: action === 'approve' ? 'approved' : 'rejected' }));
        setTimeout(() => setPending(prev => prev.filter(k => k.id !== kb.id)), 1400);
      } else {
        setError(`Failed to ${action} course`);
        setActions(prev => ({ ...prev, [kb.id]: 'idle' }));
      }
    } catch (e) {
      setError(String(e));
      setActions(prev => ({ ...prev, [kb.id]: 'idle' }));
    }
  };

  return (
    <div style={{ padding: '32px 24px', maxWidth: 860, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <span style={{ fontSize: '1.6rem' }}>📋</span>
        <div>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 700, margin: 0 }}>Course Approvals</h1>
          <p style={{ fontSize: '0.82rem', color: 'var(--muted)', margin: 0 }}>
            Review and approve or reject courses submitted by Creators before they go live.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginTop: 16 }}>{error}</div>
      )}

      <div style={{ marginTop: 24 }}>
        {loading ? (
          <div style={{ color: 'var(--muted)', padding: 32, textAlign: 'center' }}>Loading pending courses…</div>
        ) : pending.length === 0 ? (
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '40px 24px', textAlign: 'center',
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: 8 }}>✅</div>
            <p style={{ fontWeight: 700, fontSize: '1rem', margin: 0 }}>All caught up!</p>
            <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginTop: 4 }}>
              No courses are waiting for review.
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {pending.map(kb => {
              const st = actions[kb.id] ?? 'idle';
              return (
                <div key={kb.id} style={{
                  background: 'var(--surface)',
                  border: '1px solid #f59e0b',
                  borderRadius: 12,
                  padding: '20px 24px',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                }}>
                  {/* Course info */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: '1rem', fontWeight: 700 }}>{kb.name}</span>
                        <span style={{
                          background: '#fef3c7', color: '#92400e',
                          fontSize: '0.7rem', fontWeight: 600,
                          padding: '2px 8px', borderRadius: 99,
                          border: '1px solid #fde68a',
                        }}>Pending Review</span>
                      </div>
                      {kb.description && (
                        <p style={{ fontSize: '0.84rem', color: 'var(--muted)', margin: 0 }}>{kb.description}</p>
                      )}
                      {kb.created_at && (
                        <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 4 }}>
                          Submitted: {new Date(kb.created_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Reason field */}
                  <div style={{ marginTop: 14 }}>
                    <input
                      className="form-input"
                      style={{ fontSize: '0.82rem' }}
                      placeholder="Optional reason / feedback for the creator…"
                      value={reasons[kb.id] ?? ''}
                      disabled={st !== 'idle'}
                      onChange={e => setReasons(prev => ({ ...prev, [kb.id]: e.target.value }))}
                    />
                  </div>

                  {/* Action buttons */}
                  <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
                    {st === 'approved' ? (
                      <span style={{ color: '#16a34a', fontWeight: 700, fontSize: '0.9rem' }}>✓ Approved</span>
                    ) : st === 'rejected' ? (
                      <span style={{ color: '#dc2626', fontWeight: 700, fontSize: '0.9rem' }}>✗ Rejected</span>
                    ) : (
                      <>
                        <button
                          className="btn btn-brand"
                          disabled={st === 'loading'}
                          onClick={() => handle(kb, 'approve')}
                          style={{ minWidth: 110 }}
                        >
                          {st === 'loading' ? '…' : '✓ Approve'}
                        </button>
                        <button
                          className="btn btn-outline"
                          disabled={st === 'loading'}
                          onClick={() => handle(kb, 'reject')}
                          style={{ minWidth: 110, borderColor: '#dc2626', color: '#dc2626' }}
                        >
                          ✗ Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
