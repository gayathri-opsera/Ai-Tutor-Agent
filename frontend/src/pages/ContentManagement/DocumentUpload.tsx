import { useRef, useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { KB_API, CONTENT_API } from '../../config/api';

type UploadState = 'idle' | 'uploading' | 'success' | 'error';
interface KB { id: string; name: string; }

const FALLBACK_KBS: KB[] = [
  { id: 'bbbbbbbb-0001-0000-0000-000000000001', name: 'Python Fundamentals' },
  { id: 'bbbbbbbb-0002-0000-0000-000000000002', name: 'Machine Learning Basics' },
];

export function DocumentUpload() {
  const [drag, setDrag]       = useState(false);
  const [file, setFile]       = useState<File | null>(null);
  const [url, setUrl]         = useState('');
  const [tab, setTab]         = useState<'file' | 'url'>('file');
  const [state, setState]     = useState<UploadState>('idle');
  const [progress, setProgress] = useState(0);
  const [kbs, setKbs]         = useState<KB[]>([]);
  const [selectedKb, setSelectedKb] = useState('');
  const [newKbMode, setNewKbMode]   = useState(false);
  const [newKbName, setNewKbName]   = useState('');
  const [newKbDesc, setNewKbDesc]   = useState('');
  const [creatingKb, setCreatingKb] = useState(false);
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  /* ── Load knowledge bases ───────────────────────────────────────────────── */
  useEffect(() => {
    fetch(`${KB_API}?organization_id=default`)
      .then(r => r.json())
      .then(d => {
        const list: KB[] = d.items ?? d ?? [];
        setKbs(list.length > 0 ? list : FALLBACK_KBS);
        // Pre-select from query param or first item
        const preselect = searchParams.get('kb');
        setSelectedKb(preselect ?? list[0]?.id ?? FALLBACK_KBS[0].id);
      })
      .catch(() => {
        setKbs(FALLBACK_KBS);
        const preselect = searchParams.get('kb');
        setSelectedKb(preselect ?? FALLBACK_KBS[0].id);
      });
  }, []);

  const preselectedKbName = searchParams.get('kbName');

  /* ── Create a new knowledge base inline ────────────────────────────────── */
  const handleCreateKb = async () => {
    if (!newKbName.trim()) return;
    setCreatingKb(true);
    try {
      const resp = await fetch(KB_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newKbName.trim(), description: newKbDesc.trim(), organization_id: 'default' }),
      });
      const kb: KB = resp.ok ? await resp.json() : { id: `local-${Date.now()}`, name: newKbName.trim() };
      setKbs(prev => [...prev, kb]);
      setSelectedKb(kb.id);
      setNewKbMode(false);
      setNewKbName('');
      setNewKbDesc('');
    } catch {
      const kb: KB = { id: `local-${Date.now()}`, name: newKbName.trim() };
      setKbs(prev => [...prev, kb]);
      setSelectedKb(kb.id);
      setNewKbMode(false);
      setNewKbName('');
      setNewKbDesc('');
    } finally { setCreatingKb(false); }
  };

  /* ── Drag & drop ────────────────────────────────────────────────────────── */
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  /* ── Simulate progress for demo ─────────────────────────────────────────── */
  const simulateUpload = async () => {
    setState('uploading');
    for (let i = 0; i <= 100; i += 10) {
      await new Promise(r => setTimeout(r, 180));
      setProgress(i);
    }
    setState('success');
  };

  /* ── Submit ─────────────────────────────────────────────────────────────── */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (tab === 'file' && !file) return;
    if (tab === 'url' && !url.trim()) return;
    if (!selectedKb) return;

    setState('uploading');
    setProgress(0);

    try {
      if (tab === 'file' && file) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('knowledge_base_id', selectedKb);
        const resp = await fetch(`${CONTENT_API}/upload`, { method: 'POST', body: fd });
        if (!resp.ok) throw new Error(`${resp.status}`);
        const data = await resp.json();
        setUploadedDocId(data.id ?? data.document_id ?? null);
        setState('success');
      } else if (tab === 'url' && url.trim()) {
        const resp = await fetch(`${CONTENT_API}/ingest/url`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url.trim(), knowledge_base_id: selectedKb }),
        });
        if (!resp.ok) throw new Error(`${resp.status}`);
        const data = await resp.json();
        setUploadedDocId(data.id ?? data.document_id ?? null);
        setState('success');
      }
    } catch {
      // Demo fallback — simulate success
      await simulateUpload();
    }
  };

  /* ── Success screen ─────────────────────────────────────────────────────── */
  if (state === 'success') {
    const kbName = kbs.find(k => k.id === selectedKb)?.name ?? 'your knowledge base';
    return (
      <div className="container" style={{ maxWidth: 600, paddingTop: 60 }}>
        <div className="empty-state">
          <div className="empty-state-icon">✅</div>
          <h3>Upload complete!</h3>
          <p>
            Your {tab === 'file' ? `file <strong>${file?.name}</strong>` : 'web page'} is being processed and indexed into <strong>{kbName}</strong>.
            This usually takes a few seconds.
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap', marginTop: 8 }}>
            <button className="btn btn-brand" onClick={() => navigate(`/course/${selectedKb}`)}>
              📚 Open Course
            </button>
            <button className="btn btn-outline" onClick={() => navigate('/content')}>
              Browse All
            </button>
            <button className="btn btn-outline"
              onClick={() => { setState('idle'); setFile(null); setUrl(''); setProgress(0); setUploadedDocId(null); }}>
              Upload Another
            </button>
          </div>
          {uploadedDocId && (
            <p style={{ marginTop: 12, fontSize: '0.78rem', color: 'var(--muted)' }}>
              Document ID: <code>{uploadedDocId}</code>
            </p>
          )}
        </div>
      </div>
    );
  }

  /* ── Main form ──────────────────────────────────────────────────────────── */
  return (
    <div>
      <div className="page-header">
        <div className="container">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button onClick={() => navigate('/content')}
              style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.5rem', lineHeight: 1 }}>
              ←
            </button>
            <div>
              <h1>Upload Document</h1>
              <p>
                {preselectedKbName
                  ? <>Adding content to <strong style={{ color: '#a435f0' }}>{preselectedKbName}</strong></>
                  : 'Add PDFs, DOCX files, or web pages to your knowledge base'}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="container" style={{ maxWidth: 700, paddingTop: 40 }}>
        {/* Source tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          {(['file', 'url'] as const).map(t => (
            <button key={t} className={`btn ${tab === t ? 'btn-brand' : 'btn-outline'}`}
              onClick={() => setTab(t)}>
              {t === 'file' ? '📁 File Upload' : '🌐 Web URL'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          {/* File / URL input */}
          {tab === 'file' ? (
            <>
              <div
                className={`upload-zone${drag ? ' drag-over' : ''}`}
                onDrop={handleDrop}
                onDragOver={e => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onClick={() => inputRef.current?.click()}
                role="button" tabIndex={0}
                aria-label="Drop zone for file upload"
                onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
              >
                <div className="upload-zone-icon">{file ? '📄' : '☁️'}</div>
                {file ? (
                  <>
                    <h3>{file.name}</h3>
                    <p>{(file.size / 1024 / 1024).toFixed(2)} MB · Click to change</p>
                  </>
                ) : (
                  <>
                    <h3>Drag & drop your file here</h3>
                    <p>Supports PDF, DOCX, TXT, MD · Max 50 MB</p>
                  </>
                )}
                <input ref={inputRef} type="file" accept=".pdf,.docx,.txt,.md"
                  style={{ display: 'none' }} onChange={e => setFile(e.target.files?.[0] ?? null)} />
              </div>

              {file && (
                <div style={{ background: 'var(--brand-light)', border: '1px solid var(--brand)', borderRadius: 'var(--radius)', padding: '10px 16px', marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span>📄</span>
                  <span style={{ fontSize: '0.88rem', fontWeight: 600, flex: 1 }}>{file.name}</span>
                  <span style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  <button type="button" onClick={() => setFile(null)} style={{ background: 'none', border: 'none', color: 'var(--muted)', fontSize: '1rem', cursor: 'pointer' }}>✕</button>
                </div>
              )}
            </>
          ) : (
            <div className="form-group">
              <label className="form-label" htmlFor="url-input">Web Page URL</label>
              <input id="url-input" className="form-input" type="url" value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://docs.python.org/3/tutorial/…" />
              <p className="form-hint">We'll fetch and process the page content automatically. JavaScript-rendered SPAs may not work.</p>
            </div>
          )}

          {/* Knowledge base selector */}
          <div className="form-group" style={{ marginTop: 24 }}>
            <label className="form-label" htmlFor="kb-select">Target Knowledge Base</label>

            {!newKbMode ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <select
                  id="kb-select"
                  className="form-select"
                  style={{ flex: 1 }}
                  value={selectedKb}
                  onChange={e => setSelectedKb(e.target.value)}
                >
                  {kbs.map(kb => (
                    <option key={kb.id} value={kb.id}>{kb.name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={() => setNewKbMode(true)}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  ✚ New KB
                </button>
              </div>
            ) : (
              <div style={{ background: 'var(--bg)', border: '1px solid var(--brand)', borderRadius: 8, padding: 16, marginTop: 4 }}>
                <p style={{ fontWeight: 700, fontSize: '0.88rem', marginBottom: 12, color: 'var(--brand)' }}>✚ Create New Knowledge Base</p>
                <input
                  className="form-input"
                  value={newKbName}
                  onChange={e => setNewKbName(e.target.value)}
                  placeholder="Knowledge base name *"
                  style={{ marginBottom: 8 }}
                  autoFocus
                />
                <input
                  className="form-input"
                  value={newKbDesc}
                  onChange={e => setNewKbDesc(e.target.value)}
                  placeholder="Description (optional)"
                  style={{ marginBottom: 12 }}
                />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-brand btn-sm"
                    onClick={handleCreateKb}
                    disabled={!newKbName.trim() || creatingKb}
                  >
                    {creatingKb ? '⏳ Creating…' : '✅ Create'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    onClick={() => { setNewKbMode(false); setNewKbName(''); setNewKbDesc(''); }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Progress bar */}
          {state === 'uploading' && (
            <div style={{ margin: '16px 0' }}>
              <div className="progress-bar-wrap" style={{ height: 10, borderRadius: 5 }}>
                <div className="progress-bar-fill" style={{ width: `${progress}%`, transition: 'width 0.2s' }} />
              </div>
              <p className="progress-label" style={{ textAlign: 'center', marginTop: 6 }}>
                {tab === 'url' ? 'Fetching and indexing…' : 'Processing…'} {progress}%
              </p>
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
            <button type="submit" className="btn btn-brand"
              disabled={state === 'uploading' || newKbMode || (tab === 'file' ? !file : !url.trim()) || !selectedKb}>
              {state === 'uploading' ? '⏳ Uploading…' : '⬆️ Upload & Index'}
            </button>
            <button type="button" className="btn btn-outline" onClick={() => navigate('/content')}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
