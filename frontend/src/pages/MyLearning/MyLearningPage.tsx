import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KB_API } from '../../config/api';
import { useUser } from '../../auth/UserContext';

interface KB { id: string; name: string; description: string; }

const EMOJIS = ['📚','🤖','🧠','💡','🔬','🎯','⚡','🌐'];

function getProgress(kbId: string): number {
  try {
    const p = JSON.parse(localStorage.getItem(`progress_${kbId}`) ?? '{}');
    return Object.values(p).filter(Boolean).length;
  } catch { return 0; }
}

function getTotalDocs(kbId: string): number {
  const counts: Record<string, number> = {
    'bbbbbbbb-0001-0000-0000-000000000001': 2,
    'bbbbbbbb-0002-0000-0000-000000000002': 1,
  };
  return counts[kbId] ?? 1;
}

type TabFilter = 'all' | 'in_progress' | 'completed' | 'not_started';

export function MyLearningPage() {
  const [kbs, setKbs]         = useState<KB[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]         = useState<TabFilter>('all');
  const navigate              = useNavigate();
  const { user }              = useUser();

  useEffect(() => {
    fetch(`${KB_API}?organization_id=default`)
      .then(r => r.json())
      .then(d => { setKbs(d.items ?? d ?? []); setLoading(false); })
      .catch(() => {
        setKbs([
          { id: 'bbbbbbbb-0001-0000-0000-000000000001', name: 'Python Fundamentals', description: 'Core Python programming: variables, functions, OOP, and async patterns.' },
          { id: 'bbbbbbbb-0002-0000-0000-000000000002', name: 'Machine Learning Basics', description: 'Intro to supervised, unsupervised, and reinforcement learning.' },
        ]);
        setLoading(false);
      });
  }, []);

  // Compute pct for each KB for filtering
  const kbsWithProgress = kbs.map((kb, i) => {
    const done  = getProgress(kb.id);
    const total = getTotalDocs(kb.id);
    const pct   = total ? Math.round((done / total) * 100) : 0;
    return { kb, i, done, total, pct };
  });

  const filtered = kbsWithProgress.filter(({ pct }) => {
    if (tab === 'all')         return true;
    if (tab === 'completed')   return pct === 100;
    if (tab === 'in_progress') return pct > 0 && pct < 100;
    if (tab === 'not_started') return pct === 0;
    return true;
  });

  const TABS: { key: TabFilter; label: string }[] = [
    { key: 'all',         label: `All (${kbs.length})` },
    { key: 'in_progress', label: `In Progress (${kbsWithProgress.filter(x => x.pct > 0 && x.pct < 100).length})` },
    { key: 'completed',   label: `Completed (${kbsWithProgress.filter(x => x.pct === 100).length})` },
    { key: 'not_started', label: `Not Started (${kbsWithProgress.filter(x => x.pct === 0).length})` },
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
              <h3>No courses here yet</h3>
              <p>{tab === 'completed' ? 'You haven\'t completed any courses yet. Keep learning!' : tab === 'in_progress' ? 'Start a course to see it here.' : 'Browse knowledge bases to start learning.'}</p>
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
                        {pct === 100
                          ? <span className="badge badge-success">✓ Completed</span>
                          : pct > 0
                            ? <span className="badge badge-warning">In Progress</span>
                            : <span className="badge badge-gray">Not Started</span>}
                      </div>
                    </div>

                    {/* CTA */}
                    <div style={{ display: 'flex', alignItems: 'center', padding: '0 24px', borderLeft: '1px solid var(--border)' }}>
                      <button className="btn btn-brand" onClick={e => { e.stopPropagation(); navigate(`/course/${kb.id}`); }}>
                        {pct === 0 ? 'Start Course' : pct === 100 ? 'Review' : 'Continue'}
                      </button>
                    </div>
                  </div>
              ))}

              {/* Discover more */}
              <div style={{ background: 'linear-gradient(135deg,#1c1d1f 0%,#3b1f6e 100%)', borderRadius: 8, padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
                <div>
                  <h3 style={{ color: '#fff', fontWeight: 700, marginBottom: 4 }}>Add more knowledge bases</h3>
                  <p style={{ color: '#aaa', fontSize: '0.88rem' }}>Upload PDFs, DOCX files, or web pages to create new courses.</p>
                </div>
                <button className="btn btn-brand" onClick={() => navigate('/content/upload')}>+ Upload Content</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
