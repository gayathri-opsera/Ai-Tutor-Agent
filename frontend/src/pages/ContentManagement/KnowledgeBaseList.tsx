import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CourseCard } from '../../components/CourseCard';
import { KB_API } from '../../config/api';
import { apiFetch } from '../../config/apiFetch';
import { useUser } from '../../auth/UserContext';

interface KB { id: string; name: string; description: string; is_active: boolean; doc_count?: number; }

const EMOJIS  = ['📚', '🤖', '🧠', '💡', '🔬', '🎯', '⚡', '🌐'];

const FALLBACK_KBS: KB[] = [
  { id: 'bbbbbbbb-0001-0000-0000-000000000001', name: 'Python Fundamentals', description: 'Core Python programming: variables, functions, OOP, and async patterns.', is_active: true },
  { id: 'bbbbbbbb-0002-0000-0000-000000000002', name: 'Machine Learning Basics', description: 'Intro to supervised, unsupervised, and reinforcement learning.', is_active: true },
];

/* ── Confirm Delete Modal ─────────────────────────────────────────────────── */
function ConfirmDeleteModal({ kb, onClose, onConfirm, deleting }: {
  kb: KB;
  onClose: () => void;
  onConfirm: () => void;
  deleting: boolean;
}) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: '#fff', borderRadius: 12, width: '100%', maxWidth: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.25)', overflow: 'hidden' }}>
        <div style={{ background: '#fef2f2', padding: '20px 24px', borderBottom: '1px solid #fca5a5' }}>
          <h2 style={{ color: '#dc2626', fontSize: '1.05rem', fontWeight: 800, marginBottom: 4 }}>🗑 Delete Course</h2>
          <p style={{ color: '#991b1b', fontSize: '0.82rem' }}>This will archive the course and remove it from the active list.</p>
        </div>
        <div style={{ padding: '20px 24px' }}>
          <p style={{ fontSize: '0.9rem', color: 'var(--text)', marginBottom: 20 }}>
            Are you sure you want to delete <strong>"{kb.name}"</strong>?
            {kb.doc_count ? ` It contains ${kb.doc_count} document${kb.doc_count !== 1 ? 's' : ''}.` : ''}
          </p>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              className="btn"
              style={{ flex: 1, background: '#dc2626', color: '#fff', border: 'none' }}
              onClick={onConfirm}
              disabled={deleting}
            >
              {deleting ? '⏳ Deleting…' : '🗑 Yes, Delete'}
            </button>
            <button className="btn btn-outline" style={{ flex: 1 }} onClick={onClose} disabled={deleting}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Edit KB Modal ────────────────────────────────────────────────────────── */
function EditKBModal({ kb, onClose, onSave }: {
  kb: KB;
  onClose: () => void;
  onSave: (updated: KB) => void;
}) {
  const [name, setName] = useState(kb.name);
  const [desc, setDesc] = useState(kb.description ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError('Name is required.'); return; }
    setSaving(true); setError('');
    try {
      const resp = await apiFetch(`${KB_API}/${kb.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: desc.trim() }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const updated = await resp.json();
      onSave({ ...kb, ...updated });
    } catch {
      setError('Failed to save changes. Please try again.');
    } finally { setSaving(false); }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: '#fff', borderRadius: 12, width: '100%', maxWidth: 480, boxShadow: '0 20px 60px rgba(0,0,0,0.25)', overflow: 'hidden' }}>
        <div style={{ background: 'var(--header-bg)', padding: '20px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 style={{ color: '#fff', fontSize: '1.1rem', fontWeight: 800 }}>✏️ Edit Knowledge Base</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#aaa', fontSize: '1.4rem', cursor: 'pointer' }}>✕</button>
        </div>
        <form onSubmit={handleSubmit} style={{ padding: '24px' }}>
          {error && <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: '0.85rem', color: '#dc2626' }}>{error}</div>}
          <div className="form-group">
            <label className="form-label">Name *</label>
            <input className="form-input" value={name} onChange={e => setName(e.target.value)} maxLength={120} />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-input" value={desc} onChange={e => setDesc(e.target.value)} rows={3} style={{ resize: 'vertical', minHeight: 80 }} maxLength={500} />
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
            <button type="submit" className="btn btn-brand" disabled={saving || !name.trim()} style={{ flex: 1 }}>
              {saving ? '⏳ Saving…' : '✅ Save Changes'}
            </button>
            <button type="button" className="btn btn-outline" onClick={onClose} style={{ flex: 1 }}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

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
      const resp = await apiFetch(KB_API, {
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
  const [kbs, setKbs]               = useState<KB[]>([]);
  const [loading, setLoading]       = useState(true);
  const [filter, setFilter]         = useState<'all' | 'active' | 'archived'>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [editKb, setEditKb]         = useState<KB | null>(null);
  const [menuOpen, setMenuOpen]     = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<KB | null>(null);
  const [deleting, setDeleting]     = useState(false);
  const [searchParams]              = useSearchParams();
  const navigate                    = useNavigate();
  const { user }                    = useUser();

  // Enrollment state
  const [enrolledIds, setEnrolledIds]     = useState<Set<string>>(new Set());
  const [enrollingId, setEnrollingId]     = useState<string | null>(null);

  const searchQuery = searchParams.get('q')?.toLowerCase() ?? '';
  const canManage   = user?.isCreator === true || user?.isAdmin === true;
  const isLearner   = !canManage; // learners see enroll/unenroll

  const userId = user?.id ?? 'demo-user';

  const loadKbs = async () => {
    try {
      // Always fetch with include_archived so the filter can work client-side
      const r = await apiFetch(`${KB_API}?organization_id=default&include_archived=true`);
      const d = r.ok ? await r.json() : {};
      const items: KB[] = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : [];
      // Enrich each KB with doc count
      const enriched = await Promise.all(items.map(async kb => {
        try {
          const dr = await apiFetch(`${KB_API}/${kb.id}/documents`);
          const dd = await dr.json();
          return { ...kb, doc_count: (dd.items ?? []).length };
        } catch { return kb; }
      }));
      setKbs(enriched);
    } catch {
      setKbs(FALLBACK_KBS);
    } finally { setLoading(false); }
  };

  const loadEnrollments = async () => {
    try {
      const r = await apiFetch(`/api/v1/learner/enrollments?user_id=${encodeURIComponent(userId)}`);
      if (r.ok) {
        const d = await r.json();
        setEnrolledIds(new Set(d.enrolled_kb_ids ?? []));
      }
    } catch { /* ignore — enrollment is optional */ }
  };

  useEffect(() => { loadKbs(); loadEnrollments(); }, []);

  const toggleEnroll = async (kb: KB, e: React.MouseEvent) => {
    e.stopPropagation();
    setEnrollingId(kb.id);
    const isEnrolled = enrolledIds.has(kb.id);
    try {
      if (isEnrolled) {
        await apiFetch(`/api/v1/learner/enroll/${kb.id}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' });
        setEnrolledIds(prev => { const s = new Set(prev); s.delete(kb.id); return s; });
      } else {
        await apiFetch(`/api/v1/learner/enroll?user_id=${encodeURIComponent(userId)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kb_id: kb.id }),
        });
        setEnrolledIds(prev => new Set([...prev, kb.id]));
      }
    } catch { /* best-effort */ }
    finally { setEnrollingId(null); }
  };

  const handleArchive = async (kb: KB) => {
    setMenuOpen(null);
    const endpoint = kb.is_active ? `${KB_API}/${kb.id}/archive` : `${KB_API}/${kb.id}/unarchive`;
    try {
      const resp = await apiFetch(endpoint, { method: 'POST' });
      if (!resp.ok) throw new Error(`${resp.status}`);
      setKbs(prev => prev.map(k => k.id === kb.id ? { ...k, is_active: !kb.is_active } : k));
    } catch { alert('Failed to update course. Please try again.'); }
  };

  // Opens the confirm modal — replaces window.confirm() which browsers suppress
  const handleDeleteClick = (kb: KB) => {
    setMenuOpen(null);
    setDeleteTarget(kb);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const resp = await apiFetch(`${KB_API}/${deleteTarget.id}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error(`Server returned ${resp.status}`);
      setKbs(prev => prev.filter(k => k.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (err) {
      alert(`Failed to delete "${deleteTarget.name}". ${err instanceof Error ? err.message : ''}`);
    } finally {
      setDeleting(false);
    }
  };

  // Auto-open create modal when ?create=1 is in URL
  useEffect(() => {
    if (searchParams.get('create') === '1' && canManage) setShowCreate(true);
  }, [searchParams, canManage]);

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
    setKbs(prev => [{ ...kb, is_active: true }, ...prev]);
    setShowCreate(false);
    navigate(`/content/upload?kb=${kb.id}&kbName=${encodeURIComponent(kb.name)}`);
  };

  const handleEdited = (updated: KB) => {
    setKbs(prev => prev.map(k => k.id === updated.id ? { ...k, ...updated } : k));
    setEditKb(null);
  };

  return (
    <div onClick={() => setMenuOpen(null)}>
      {showCreate && <CreateKBModal onClose={() => setShowCreate(false)} onCreate={handleCreated} />}
      {editKb && <EditKBModal kb={editKb} onClose={() => setEditKb(null)} onSave={handleEdited} />}
      {deleteTarget && (
        <ConfirmDeleteModal
          kb={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDeleteConfirm}
          deleting={deleting}
        />
      )}

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
              {canManage && (
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
              {!searchQuery && canManage && (
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
                <div key={kb.id} style={{ position: 'relative' }}>
                  {/* Archive indicator */}
                  {!kb.is_active && (
                    <div style={{ position: 'absolute', top: 8, left: 8, zIndex: 2, background: '#f3f4f6', color: '#6b7280', fontSize: '0.7rem', fontWeight: 700, padding: '2px 8px', borderRadius: 6 }}>
                      📦 Archived
                    </div>
                  )}
                  {/* Action menu — only for creators/admins */}
                  {canManage && (
                    <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 10 }}
                      onClick={e => e.stopPropagation()}>
                      <button
                        style={{ background: 'rgba(0,0,0,0.5)', color: '#fff', border: 'none', borderRadius: 6, width: 28, height: 28, cursor: 'pointer', fontSize: '0.9rem', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                        onClick={() => setMenuOpen(menuOpen === kb.id ? null : kb.id)}
                        title="Course actions"
                      >⋯</button>
                      {menuOpen === kb.id && (
                        <div style={{ position: 'absolute', right: 0, top: 32, background: '#fff', border: '1px solid var(--border)', borderRadius: 8, boxShadow: '0 4px 20px rgba(0,0,0,0.15)', minWidth: 160, zIndex: 100 }}>
                          <button onClick={() => { setEditKb(kb); setMenuOpen(null); }}
                            style={{ display: 'block', width: '100%', padding: '10px 16px', textAlign: 'left', border: 'none', background: 'none', cursor: 'pointer', fontSize: '0.85rem' }}>
                            ✏️ Edit name & description
                          </button>
                          <button onClick={() => handleArchive(kb)}
                            style={{ display: 'block', width: '100%', padding: '10px 16px', textAlign: 'left', border: 'none', background: 'none', cursor: 'pointer', fontSize: '0.85rem' }}>
                            {kb.is_active ? '📦 Archive course' : '✅ Unarchive course'}
                          </button>
                          <hr style={{ margin: '4px 0', border: 'none', borderTop: '1px solid var(--border)' }} />
                          <button onClick={() => handleDeleteClick(kb)}
                            style={{ display: 'block', width: '100%', padding: '10px 16px', textAlign: 'left', border: 'none', background: 'none', cursor: 'pointer', fontSize: '0.85rem', color: '#dc2626' }}>
                            🗑 Delete course
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  <CourseCard
                    id={kb.id}
                    name={kb.name}
                    description={kb.description}
                    emoji={EMOJIS[i % EMOJIS.length]}
                    docCount={kb.doc_count ?? 0}
                    tag={kb.is_active ? 'Active' : 'Archived'}
                  />
                  {/* Enroll / Unenroll button — shown for learners on active courses */}
                  {isLearner && kb.is_active && (
                    <div style={{ position: 'absolute', bottom: 46, right: 12, zIndex: 5 }}
                      onClick={e => e.stopPropagation()}>
                      <button
                        onClick={e => toggleEnroll(kb, e)}
                        disabled={enrollingId === kb.id}
                        style={{
                          padding: '5px 14px', borderRadius: 20, fontSize: '0.78rem', fontWeight: 700,
                          cursor: enrollingId === kb.id ? 'wait' : 'pointer', border: '2px solid',
                          background:    enrolledIds.has(kb.id) ? '#d1fae5' : '#a435f0',
                          color:         enrolledIds.has(kb.id) ? '#065f46' : '#fff',
                          borderColor:   enrolledIds.has(kb.id) ? '#6ee7b7' : '#a435f0',
                          transition:    'all 0.15s',
                        }}
                      >
                        {enrollingId === kb.id ? '…' : enrolledIds.has(kb.id) ? '✓ Enrolled' : '+ Enroll'}
                      </button>
                    </div>
                  )}
                </div>
              ))}

              {/* Create new card — only for Creator/Admin */}
              {canManage && (
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
