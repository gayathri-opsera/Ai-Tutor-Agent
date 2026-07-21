import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KB_API } from '../../config/api';
import { useUser } from '../../auth/UserContext';
import { apiFetch } from '../../config/apiFetch';

interface KB {
  id: string;
  name: string;
  description: string;
  doc_count: number;
}

interface KBProgress {
  completed_count: number;
  completed_doc_ids: string[];
}

const EMOJIS = ['📚','🤖','🧠','💡','🔬','🎯','⚡','🌐'];

function decodeTitle(raw: string): string {
  try { return decodeURIComponent(raw); } catch { return raw; }
}

/** Completed count from server progress, falling back to localStorage. */
function getLocalDone(kbId: string): number {
  try {
    const p = JSON.parse(localStorage.getItem(`progress_${kbId}`) ?? '{}');
    return Object.values(p).filter(Boolean).length;
  } catch { return 0; }
}

type TabFilter = 'all' | 'in_progress' | 'completed' | 'not_started';

export function MyLearningPage() {
  const [kbs, setKbs]                   = useState<KB[]>([]);
  const [serverProgress, setProgress]   = useState<Record<string, KBProgress>>({});
  const [loading, setLoading]           = useState(true);
  const [tab, setTab]                   = useState<TabFilter>('all');
  const navigate                        = useNavigate();
  const { user }                        = useUser();

  const userId = user?.id ?? 'demo-user';
  const canManage = user?.isCreator === true || user?.isAdmin === true;

  useEffect(() => {
    // Fetch enrollments first, then load only those KBs
    Promise.all([
      apiFetch(`${KB_API}?organization_id=default`).then(r => r.ok ? r.json() : {}),
      apiFetch(`/api/v1/learner/enrollments?user_id=${encodeURIComponent(userId)}`).then(r => r.ok ? r.json() : { enrolled_kb_ids: [] }),
    ])
      .then(async ([kbData, enrollData]) => {
        const allItems: KB[] = (Array.isArray(kbData?.items) ? kbData.items : Array.isArray(kbData) ? kbData : [])
          .map((kb: KB) => ({ ...kb, name: decodeTitle(kb.name) }));
        const enrolledSet = new Set<string>(enrollData.enrolled_kb_ids ?? []);
        // Only show enrolled courses on My Learning
        const items = allItems.filter(kb => enrolledSet.has(kb.id));
        setKbs(items);
        setLoading(false);

        // Fetch server-side lesson progress for each enrolled KB in parallel.
        const entries = await Promise.all(
          items.map(async (kb) => {
            try {
              const r = await apiFetch(
                `/api/v1/learner/course/${kb.id}/progress?user_id=${encodeURIComponent(userId)}`
              );
              if (r.ok) {
                const data: KBProgress = await r.json();
                return [kb.id, data] as const;
              }
            } catch { /* ignore */ }
            const done = getLocalDone(kb.id);
            return [kb.id, { completed_count: done, completed_doc_ids: [] }] as const;
          })
        );
        setProgress(Object.fromEntries(entries));
      })
      .catch(() => {
        setKbs([]);
        setLoading(false);
      });
  }, [userId]);

  const kbsWithProgress = kbs.map((kb, i) => {
    const serverDone = serverProgress[kb.id]?.completed_count;
    // Prefer server count; fall back to localStorage
    const done  = serverDone != null ? serverDone : getLocalDone(kb.id);
    const total = kb.doc_count > 0 ? kb.doc_count : 1;
    const pct   = Math.min(100, Math.round((done / total) * 100));
    return { kb, i, done, total, pct };
  });

  const filtered = kbsWithProgress.filter(({ pct, done }) => {
    if (tab === 'all')         return true;
    if (tab === 'completed')   return pct === 100 && done > 0;
    if (tab === 'in_progress') return pct > 0 && pct < 100;
    if (tab === 'not_started') return done === 0;
    return true;
  });

  const TABS: { key: TabFilter; label: string }[] = [
    { key: 'all',         label: `All (${kbs.length})` },
    { key: 'in_progress', label: `In Progress (${kbsWithProgress.filter(x => x.pct > 0 && x.pct < 100).length})` },
    { key: 'completed',   label: `Completed (${kbsWithProgress.filter(x => x.pct === 100 && x.done > 0).length})` },
    { key: 'not_started', label: `Not Started (${kbsWithProgress.filter(x => x.done === 0).length})` },
  ];

  return (
    <div>
      <div className="page-header">
        <div className="container">
          <h1>My Learning</h1>
          <p>Welcome back, {user?.name?.split(' ')[0]}! Continue where you left off.</p>
        </div>
      </div>

      <div className="container">
        <div className="section">
          {/* Tabs */}
          <div className="flex gap-2 mb-6" style={{ flexWrap: 'wrap' }}>
            {TABS.map(t => (
              <button
                key={t.key}
                className={`btn btn-sm ${tab === t.key ? 'btn-brand' : 'btn-outline'}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {loading && <div className="empty-state"><div className="empty-state-icon">⏳</div><h3>Loading…</h3></div>}

          {!loading && filtered.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon">📭</div>
              <h3>{kbs.length === 0 ? "You haven't enrolled in any courses yet" : 'No courses here yet'}</h3>
              <p>{kbs.length === 0 ? 'Browse the course catalogue and click "+ Enroll" to add courses to your learning path.' : tab === 'completed' ? "You haven't completed any courses yet. Keep learning!" : tab === 'in_progress' ? 'Start a course to see it here.' : 'Browse knowledge bases to start learning.'}</p>
              <button className="btn btn-brand" onClick={() => navigate('/content')}>Browse Courses</button>
            </div>
          )}

          {!loading && filtered.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {filtered.map(({ kb, i, done, total, pct }) => (
                <div key={kb.id}
                  style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', display: 'flex', cursor: 'pointer', boxShadow: 'var(--shadow-sm)', transition: 'box-shadow 0.2s' }}
                  onClick={() => navigate(`/course/${kb.id}`)}
                  onMouseEnter={e => (e.currentTarget.style.boxShadow = 'var(--shadow-lg)')}
                  onMouseLeave={e => (e.currentTarget.style.boxShadow = 'var(--shadow-sm)')}
                >
                  {/* Thumbnail */}
                  <div style={{ width: 200, minWidth: 200, background: 'linear-gradient(135deg,#1c1d1f 0%,#3b1f6e 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '3rem' }}>
                    {EMOJIS[i % EMOJIS.length]}
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, padding: '20px 24px' }}>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 4 }}>{kb.name}</h3>
                    <p style={{ fontSize: '0.84rem', color: 'var(--muted)', marginBottom: 12, lineHeight: 1.4 }}>{kb.description}</p>

                    {/* Progress bar */}
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: 4 }}>
                        <span style={{ color: 'var(--muted)' }}>{done}/{total} lessons complete</span>
                        <span style={{ fontWeight: 700, color: 'var(--brand)' }}>{pct}%</span>
                      </div>
                      <div className="progress-bar-wrap" style={{ height: 8 }}>
                        <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: 8 }}>
                      <span className="badge badge-brand">{total} lesson{total !== 1 ? 's' : ''}</span>
                      {pct === 100 && done > 0
                        ? <span className="badge badge-success">✓ Completed</span>
                        : pct > 0
                          ? <span className="badge badge-warning">In Progress</span>
                          : <span className="badge badge-gray">Not Started</span>}
                    </div>
                  </div>

                  {/* CTA */}
                  <div style={{ display: 'flex', alignItems: 'center', padding: '0 24px', borderLeft: '1px solid var(--border)' }}>
                    <button className="btn btn-brand" onClick={e => { e.stopPropagation(); navigate(`/course/${kb.id}`); }}>
                      {done === 0 ? 'Start Course' : pct === 100 ? 'Review' : 'Continue'}
                    </button>
                  </div>
                </div>
              ))}

              {/* Discover more — only shown to creators/admins */}
              {canManage && (
              <div style={{ background: 'linear-gradient(135deg,#1c1d1f 0%,#3b1f6e 100%)', borderRadius: 8, padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
                <div>
                  <h3 style={{ color: '#fff', fontWeight: 700, marginBottom: 4 }}>Add more knowledge bases</h3>
                  <p style={{ color: '#aaa', fontSize: '0.88rem' }}>Upload PDFs, DOCX files, or web pages to create new courses.</p>
                </div>
                <button className="btn btn-brand" onClick={() => navigate('/content/upload')}>+ Upload Content</button>
              </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
