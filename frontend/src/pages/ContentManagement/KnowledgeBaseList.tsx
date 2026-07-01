import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CourseCard } from '../../components/CourseCard';
import { KB_API } from '../../config/api';
import { useUser } from '../../auth/UserContext';

interface KB { id: string; name: string; description: string; is_active: boolean; }

const EMOJIS  = ['📚', '🤖', '🧠', '💡', '🔬', '🎯', '⚡', '🌐'];
const RATINGS = [4.7, 4.5, 4.8, 4.3, 4.6, 4.9];

const FALLBACK_KBS: KB[] = [
  { id: 'bbbbbbbb-0001-0000-0000-000000000001', name: 'Python Fundamentals', description: 'Core Python programming: variables, functions, OOP, and async patterns.', is_active: true },
  { id: 'bbbbbbbb-0002-0000-0000-000000000002', name: 'Machine Learning Basics', description: 'Intro to supervised, unsupervised, and reinforcement learning.', is_active: true },
];

/* ── Create KB Modal ──────────────────────────────────────────────────────── */
function CreateKBModal({ onClose, onCreate }: {
  onClose: () => void;
  onCreate: (kb: KB) => void;
}) {
  const [name, setName]     = useState('');
  const [desc, setDesc]     = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => { nameRef.current?.focus(); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError('Please enter a name for your knowledge base.'); return; }
    setSaving(true); setError('');
    try {
      const resp = await fetch(KB_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: desc.trim(), organization_id: 'default' }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const kb: KB = await resp.json();
      onCreate({ ...kb, is_active: true });
    } catch {
      // Demo fallback — create locally
      const kb: KB = {
        id: `local-${Date.now()}`,
        name: name.trim(),
        description: desc.trim(),
        is_active: true,
      };
      onCreate(kb);
    } finally { setSaving(false); }
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{ background: '#fff', borderRadius: 12, width: '100%', maxWidth: 480, boxShadow: '0 20px 60px rgba(0,0,0,0.25)', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ background: 'var(--header-bg)', padding: '20px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ color: '#fff', fontSize: '1.1rem', fontWeight: 800, marginBottom: 2 }}>📚 Create Knowledge Base</h2>
            <p style={{ color: '#aaa', fontSize: '0.8rem' }}>Give your course a name and description</p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#aaa', fontSize: '1.4rem', cursor: 'pointer', lineHeight: 1 }}>✕</button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ padding: '24px' }}>
          {error && (
            <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: '0.85rem', color: '#dc2626' }}>
              {error}
            </div>
          )}

          <div className="form-group">
            <label className="form-label" htmlFor="kb-name">Knowledge Base Name *</label>
            <input
              ref={nameRef}
              id="kb-name"
              className="form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Advanced JavaScript, HIPAA Compliance…"
              maxLength={120}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="kb-desc">Description</label>
            <textarea
              id="kb-desc"
              className="form-input"
              value={desc}
              onChange={e => setDesc(e.target.value)}
              placeholder="What will learners find in this knowledge base?"
              rows={3}
              style={{ resize: 'vertical', minHeight: 80 }}
              maxLength={500}
            />
            <p className="form-hint">{desc.length}/500 characters</p>
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
            <button type="submit" className="btn btn-brand" disabled={saving || !name.trim()} style={{ flex: 1 }}>
              {saving ? '⏳ Creating…' : '✅ Create Knowledge Base'}
            </button>
            <button type="button" className="btn btn-outline" onClick={onClose} style={{ flex: 1 }}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Main page ────────────────────────────────────────────────────────────── */
export function KnowledgeBaseList() {
  const [kbs, setKbs]             = useState<KB[]>([]);
  const [loading, setLoading]     = useState(true);
  const [filter, setFilter]       = useState<'all' | 'active' | 'archived'>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [searchParams]            = useSearchParams();
  const navigate                  = useNavigate();
  const { user }                  = useUser();

  const searchQuery = searchParams.get('q')?.toLowerCase() ?? '';
  const canCreate   = user?.role === 'Creator' || user?.role === 'Admin';

  useEffect(() => {
    fetch(`${KB_API}?organization_id=default`)
      .then(r => r.json())
      .then(d => { setKbs(d.items ?? d ?? []); setLoading(false); })
      .catch(() => { setKbs(FALLBACK_KBS); setLoading(false); });
  }, []);

  // Auto-open create modal when ?create=1 is in URL
  useEffect(() => {
    if (searchParams.get('create') === '1' && canCreate) setShowCreate(true);
  }, [searchParams, canCreate]);

  /* Apply filter + search */
  const visible = kbs.filter(kb => {
    const matchesFilter =
      filter === 'all'      ? true :
      filter === 'active'   ? kb.is_active :
      /* archived */          !kb.is_active;
    const matchesSearch = !searchQuery ||
      kb.name.toLowerCase().includes(searchQuery) ||
      kb.description?.toLowerCase().includes(searchQuery);
    return matchesFilter && matchesSearch;
  });

  const handleCreated = (kb: KB) => {
    setKbs(prev => [kb, ...prev]);
    setShowCreate(false);
    // Navigate to upload so they can populate the new KB immediately
    navigate(`/content/upload?kb=${kb.id}&kbName=${encodeURIComponent(kb.name)}`);
  };

  return (
    <div>
      {showCreate && <CreateKBModal onClose={() => setShowCreate(false)} onCreate={handleCreated} />}

      {/* Page header */}
      <div className="page-header">
        <div className="container">
          <div className="page-header-row">
            <div>
              <h1>Browse Knowledge Bases</h1>
              <p>
                {searchQuery ? `Search results for "${searchQuery}" · ` : ''}
                {visible.length} knowledge base{visible.length !== 1 ? 's' : ''}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              {canCreate && (
                <button className="btn btn-brand" onClick={() => setShowCreate(true)}>
                  ✚ Create New Course
                </button>
              )}
              <button className="btn btn-outline" onClick={() => navigate('/content/upload')}>
                ⬆️ Upload Document
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="container">
        <div className="section">
          {/* Search feedback */}
          {searchQuery && (
            <div style={{ background: 'var(--brand-light)', border: '1px solid var(--brand)', borderRadius: 8, padding: '10px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.88rem' }}>🔍 Showing results for <strong>"{searchQuery}"</strong></span>
              <button onClick={() => navigate('/content')} style={{ background: 'none', border: 'none', color: 'var(--brand)', cursor: 'pointer', fontWeight: 700, fontSize: '0.85rem' }}>Clear ✕</button>
            </div>
          )}

          {/* Filter bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
            {(['all', 'active', 'archived'] as const).map(f => (
              <button
                key={f}
                className={`btn btn-sm ${filter === f ? 'btn-brand' : 'btn-outline'}`}
                onClick={() => setFilter(f)}
              >
                {f === 'all' ? 'All' : f === 'active' ? '✅ Active' : '📦 Archived'}
              </button>
            ))}
            <span style={{ marginLeft: 'auto', fontSize: '0.82rem', color: 'var(--muted)' }}>
              {visible.length} result{visible.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Loading */}
          {loading && (
            <div className="empty-state">
              <div className="empty-state-icon">⏳</div>
              <h3>Loading knowledge bases…</h3>
            </div>
          )}

          {/* Empty state */}
          {!loading && visible.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon">{searchQuery ? '🔍' : '📭'}</div>
              <h3>{searchQuery ? 'No results found' : 'No knowledge bases yet'}</h3>
              <p>
                {searchQuery
                  ? `No knowledge bases match "${searchQuery}". Try a different search term.`
                  : 'Upload your first document to create a knowledge base and start learning.'}
              </p>
              {!searchQuery && canCreate && (
                <button className="btn btn-brand" onClick={() => setShowCreate(true)}>
                  ✚ Create First Knowledge Base
                </button>
              )}
            </div>
          )}

          {/* Cards grid */}
          {!loading && visible.length > 0 && (
            <div className="cards-grid">
              {visible.map((kb, i) => (
                <CourseCard
                  key={kb.id}
                  id={kb.id}
                  name={kb.name}
                  description={kb.description}
                  emoji={EMOJIS[i % EMOJIS.length]}
                  docCount={i === 0 ? 2 : 1}
                  rating={RATINGS[i % RATINGS.length]}
                  ratingCount={800 + i * 320}
                  tag={kb.is_active ? 'Active' : 'Archived'}
                />
              ))}

              {/* Create new card — only for Creator/Admin */}
              {canCreate && (
                <article
                  className="course-card"
                  style={{ border: '2px dashed var(--brand)', background: 'var(--brand-light)', boxShadow: 'none', cursor: 'pointer', opacity: 0.9 }}
                  onClick={() => setShowCreate(true)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && setShowCreate(true)}
                >
                  <div className="course-thumb" style={{ background: 'transparent', border: 'none' }}>
                    <span style={{ fontSize: '3rem' }}>➕</span>
                  </div>
                  <div className="course-body" style={{ textAlign: 'center', alignItems: 'center', display: 'flex', flexDirection: 'column' }}>
                    <h3 className="course-title" style={{ color: 'var(--brand)' }}>Create New Knowledge Base</h3>
                    <p className="course-instructor">Upload PDF, DOCX, or paste a URL to build a new course</p>
                  </div>
                  <div className="course-footer" style={{ justifyContent: 'center' }}>
                    <button className="btn btn-brand btn-sm">Get Started →</button>
                  </div>
                </article>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
