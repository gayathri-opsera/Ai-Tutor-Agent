import { useRef, useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { KB_API, CONTENT_API } from '../../config/api';
import { apiFetch } from '../../config/apiFetch';

type FileStatus = 'pending' | 'uploading' | 'success' | 'error';
interface FileEntry {
  file: File;
  status: FileStatus;
  error?: string;
  docId?: string;
}

interface KB { id: string; name: string; }

const FALLBACK_KBS: KB[] = [
  { id: 'bbbbbbbb-0001-0000-0000-000000000001', name: 'Python Fundamentals' },
  { id: 'bbbbbbbb-0002-0000-0000-000000000002', name: 'Machine Learning Basics' },
];

const ACCEPTED = '.pdf,.docx,.txt,.md,.mp4,.mp3,.wav,.webm,.m4a,.ogg';
const isMedia = (name: string) => /\.(mp4|mp3|wav|webm|m4a|ogg)$/i.test(name);

function fileIcon(name: string) {
  if (isMedia(name)) return '🎬';
  if (/\.pdf$/i.test(name)) return '📕';
  return '📄';
}

function humanSize(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

export function DocumentUpload() {
  const [drag, setDrag]               = useState(false);
  const [entries, setEntries]         = useState<FileEntry[]>([]);
  const [url, setUrl]                 = useState('');
  const [tab, setTab]                 = useState<'file' | 'url'>('file');
  const [uploading, setUploading]     = useState(false);
  const [allDone, setAllDone]         = useState(false);
  const [urlError, setUrlError]       = useState('');
  const [kbs, setKbs]                 = useState<KB[]>([]);
  const [selectedKb, setSelectedKb]   = useState('');
  const [newKbMode, setNewKbMode]     = useState(false);
  const [newKbName, setNewKbName]     = useState('');
  const [newKbDesc, setNewKbDesc]     = useState('');
  const [creatingKb, setCreatingKb]   = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedKbName = searchParams.get('kbName');

  /* ── Load KBs ─────────────────────────────────────────────────────────────── */
  const loadKbs = () => {
    const preselect = searchParams.get('kb');
    apiFetch(`${KB_API}?organization_id=default`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(async (d) => {
        const list: KB[] = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : [];
        const base = list.length > 0 ? list : FALLBACK_KBS;
        // If a specific KB is pre-selected (e.g. newly created) and not in the list,
        // fetch it individually so it always appears as an option.
        if (preselect && !base.find(k => k.id === preselect)) {
          try {
            const r2 = await apiFetch(`${KB_API}/${preselect}`);
            if (r2.ok) {
              const kb: KB = await r2.json();
              setKbs([kb, ...base]);
              setSelectedKb(preselect);
              return;
            }
          } catch { /* ignore, fall through */ }
        }
        setKbs(base);
        setSelectedKb(prev => prev || preselect || base[0]?.id || FALLBACK_KBS[0].id);
      })
      .catch(() => {
        setKbs(FALLBACK_KBS);
        setSelectedKb(prev => prev || preselect || FALLBACK_KBS[0].id);
      });
  };

  useEffect(() => { loadKbs(); }, []);

  /* ── Add files (dedup by name) ────────────────────────────────────────────── */
  const addFiles = (incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    setEntries(prev => {
      const existingNames = new Set(prev.map(e => e.file.name));
      const fresh = arr
        .filter(f => !existingNames.has(f.name))
        .map(f => ({ file: f, status: 'pending' as FileStatus }));
      return [...prev, ...fresh];
    });
  };

  const removeEntry = (name: string) =>
    setEntries(prev => prev.filter(e => e.file.name !== name));

  /* ── Drag & drop ──────────────────────────────────────────────────────────── */
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  /* ── Create KB inline ─────────────────────────────────────────────────────── */
  const handleCreateKb = async () => {
    if (!newKbName.trim()) return;
    setCreatingKb(true);
    try {
      const resp = await apiFetch(KB_API, {
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
      // Kick off re-index so any existing content is immediately searchable.
      if (resp.ok) apiFetch(`${CONTENT_API}/reindex-kb/${kb.id}`, { method: 'POST' }).catch(() => {});
    } catch {
      const kb: KB = { id: `local-${Date.now()}`, name: newKbName.trim() };
      setKbs(prev => [...prev, kb]);
      setSelectedKb(kb.id);
      setNewKbMode(false);
      setNewKbName('');
      setNewKbDesc('');
    } finally { setCreatingKb(false); }
  };

  /* ── Upload all pending files sequentially ───────────────────────────────── */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (tab === 'url') {
      if (!url.trim()) return;
      setUploading(true);
      setUrlError('');
      try {
        const resp = await apiFetch(`${CONTENT_API}/ingest/url`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url.trim(), knowledge_base_id: selectedKb }),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setUrlError(err.detail ?? err.message ?? `Server error (${resp.status})`);
        } else {
          // Kick off background re-index for the KB.
          apiFetch(`${CONTENT_API}/reindex-kb/${selectedKb}`, { method: 'POST' }).catch(() => {});
          setAllDone(true);
        }
      } catch (err) {
        setUrlError(err instanceof Error ? err.message : 'Network error');
      } finally { setUploading(false); }
      return;
    }

    // File mode — upload sequentially
    const pending = entries.filter(e => e.status === 'pending');
    if (!pending.length || !selectedKb) return;

    setUploading(true);
    for (const entry of pending) {
      // Mark as uploading
      setEntries(prev => prev.map(e =>
        e.file.name === entry.file.name ? { ...e, status: 'uploading' } : e
      ));

      try {
        const fd = new FormData();
        fd.append('file', entry.file);
        fd.append('knowledge_base_id', selectedKb);
        const resp = await apiFetch(`${CONTENT_API}/upload`, { method: 'POST', body: fd });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          const msg = err.detail ?? err.message ?? `Server error (${resp.status})`;
          setEntries(prev => prev.map(e =>
            e.file.name === entry.file.name ? { ...e, status: 'error', error: msg } : e
          ));
        } else {
          const data = await resp.json();
          setEntries(prev => prev.map(e =>
            e.file.name === entry.file.name
              ? { ...e, status: 'success', docId: data.id ?? data.document_id }
              : e
          ));
          // Kick off a re-index for the KB so RAG finds the new content immediately.
          // Fire-and-forget; errors are non-critical.
          apiFetch(`${CONTENT_API}/reindex-kb/${selectedKb}`, { method: 'POST' }).catch(() => {});
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Network error';
        setEntries(prev => prev.map(e =>
          e.file.name === entry.file.name ? { ...e, status: 'error', error: msg } : e
        ));
      }
    }

    setUploading(false);
    setAllDone(true);
  };

  const hasPending   = entries.some(e => e.status === 'pending');
  const hasSucceeded = entries.some(e => e.status === 'success');
  const hasFailed    = entries.some(e => e.status === 'error');

  /* ── URL success ──────────────────────────────────────────────────────────── */
  if (tab === 'url' && allDone) {
    return (
      <div className="container" style={{ maxWidth: 600, paddingTop: 60 }}>
        <div className="empty-state">
          <div className="empty-state-icon">✅</div>
          <h3>Web page queued!</h3>
          <p>The page is being fetched and indexed into <strong>{kbs.find(k => k.id === selectedKb)?.name}</strong>.</p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 16, flexWrap: 'wrap' }}>
            <button className="btn btn-brand" onClick={() => navigate(`/course/${selectedKb}`)}>Open Course</button>
            <button className="btn btn-outline" onClick={() => { setAllDone(false); setUrl(''); }}>Add Another</button>
          </div>
        </div>
      </div>
    );
  }

  /* ── Main form ────────────────────────────────────────────────────────────── */
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
              <h1>Upload Documents</h1>
              <p>
                {preselectedKbName
                  ? <>Adding content to <strong style={{ color: '#a435f0' }}>{preselectedKbName}</strong></>
                  : 'Add PDFs, DOCX, media files, or web pages to your knowledge base'}
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
          {tab === 'file' ? (
            <>
              {/* Drop zone */}
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
                <div className="upload-zone-icon">☁️</div>
                <h3>Drag & drop files here</h3>
                <p>Supports PDF, DOCX, TXT, MD, MP4, MP3, WAV, WebM · Max 50 MB each</p>
                <p style={{ fontSize: '0.78rem', color: 'var(--brand)', fontWeight: 600, marginTop: 4 }}>
                  Click to select one or multiple files
                </p>
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  accept={ACCEPTED}
                  style={{ display: 'none' }}
                  onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ''; }}
                />
              </div>

              {/* File list */}
              {entries.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>
                      {entries.length} file{entries.length > 1 ? 's' : ''} selected
                    </span>
                    {entries.some(e => e.status === 'pending') && (
                      <button type="button" className="btn btn-outline btn-sm"
                        onClick={() => setEntries([])} style={{ fontSize: '0.75rem' }}>
                        Clear all
                      </button>
                    )}
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {entries.map(entry => (
                      <div key={entry.file.name} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 14px', borderRadius: 10,
                        background: entry.status === 'success' ? '#f0fdf4'
                                  : entry.status === 'error' ? '#fef2f2'
                                  : entry.status === 'uploading' ? 'var(--brand-light)'
                                  : 'var(--bg)',
                        border: `1px solid ${
                          entry.status === 'success' ? '#86efac'
                          : entry.status === 'error' ? '#fca5a5'
                          : entry.status === 'uploading' ? 'var(--brand)'
                          : 'var(--border)'
                        }`,
                      }}>
                        <span style={{ fontSize: '1.2rem', flexShrink: 0 }}>{fileIcon(entry.file.name)}</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontWeight: 600, fontSize: '0.85rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {entry.file.name}
                          </p>
                          <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: 1 }}>
                            {humanSize(entry.file.size)}
                          </p>
                          {entry.status === 'error' && (
                            <p style={{ fontSize: '0.72rem', color: '#dc2626', marginTop: 2 }}>{entry.error}</p>
                          )}
                        </div>
                        {/* Status badge */}
                        {entry.status === 'uploading' && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--brand)', fontWeight: 700, flexShrink: 0 }}>
                            ⏳ Uploading…
                          </span>
                        )}
                        {entry.status === 'success' && (
                          <span style={{ fontSize: '0.72rem', color: '#166534', fontWeight: 700, flexShrink: 0 }}>
                            ✓ Done
                          </span>
                        )}
                        {entry.status === 'error' && (
                          <span style={{ fontSize: '0.72rem', color: '#dc2626', fontWeight: 700, flexShrink: 0 }}>
                            ✗ Failed
                          </span>
                        )}
                        {/* Remove button — only for pending files */}
                        {entry.status === 'pending' && (
                          <button type="button"
                            onClick={() => removeEntry(entry.file.name)}
                            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '0.9rem', flexShrink: 0 }}
                            aria-label={`Remove ${entry.file.name}`}>
                            ✕
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Post-upload summary */}
                  {allDone && (
                    <div style={{
                      marginTop: 16, padding: '14px 18px', borderRadius: 10,
                      background: hasFailed ? '#fef9c3' : '#f0fdf4',
                      border: `1px solid ${hasFailed ? '#fbbf24' : '#86efac'}`,
                    }}>
                      <p style={{ fontWeight: 700, fontSize: '0.9rem', marginBottom: 4 }}>
                        {hasSucceeded && !hasFailed && '✅ All files uploaded successfully!'}
                        {hasFailed && hasSucceeded && '⚠️ Some files failed — see above.'}
                        {hasFailed && !hasSucceeded && '❌ All uploads failed — please try again.'}
                      </p>
                      <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
                        {hasSucceeded && (
                          <button className="btn btn-brand btn-sm"
                            onClick={() => navigate(`/course/${selectedKb}`)}>
                            Open Course
                          </button>
                        )}
                        <button className="btn btn-outline btn-sm"
                          onClick={() => {
                            setEntries(prev => prev.filter(e => e.status !== 'success'));
                            setAllDone(false);
                          }}>
                          {hasFailed ? 'Retry Failed Files' : 'Upload More'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="form-group">
              <label className="form-label" htmlFor="url-input">Web Page URL</label>
              <input id="url-input" className="form-input" type="url" value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://docs.python.org/3/tutorial/…" />
              <p className="form-hint">We'll fetch and extract the text automatically. Works with most blogs, docs, and wikis. Very dynamic SPAs (React/Vue apps) may need saving as HTML first.</p>
              {urlError && <p style={{ color: '#dc2626', fontSize: '0.82rem', marginTop: 6 }}>{urlError}</p>}
            </div>
          )}

          {/* Knowledge base selector */}
          <div className="form-group" style={{ marginTop: 24 }}>
            <label className="form-label" htmlFor="kb-select">Target Knowledge Base</label>
            {!newKbMode ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <select id="kb-select" className="form-select" style={{ flex: 1 }}
                  value={selectedKb} onChange={e => setSelectedKb(e.target.value)}>
                  {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
                </select>
                <button type="button" className="btn btn-outline btn-sm"
                  onClick={loadKbs} title="Refresh course list" style={{ whiteSpace: 'nowrap' }}>
                  ↻
                </button>
                <button type="button" className="btn btn-outline btn-sm"
                  onClick={() => setNewKbMode(true)} style={{ whiteSpace: 'nowrap' }}>
                  ✚ New KB
                </button>
              </div>
            ) : (
              <div style={{ background: 'var(--bg)', border: '1px solid var(--brand)', borderRadius: 8, padding: 16, marginTop: 4 }}>
                <p style={{ fontWeight: 700, fontSize: '0.88rem', marginBottom: 12, color: 'var(--brand)' }}>✚ Create New Knowledge Base</p>
                <input className="form-input" value={newKbName} onChange={e => setNewKbName(e.target.value)}
                  placeholder="Knowledge base name *" style={{ marginBottom: 8 }} autoFocus />
                <input className="form-input" value={newKbDesc} onChange={e => setNewKbDesc(e.target.value)}
                  placeholder="Description (optional)" style={{ marginBottom: 12 }} />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="btn btn-brand btn-sm"
                    onClick={handleCreateKb} disabled={!newKbName.trim() || creatingKb}>
                    {creatingKb ? '⏳ Creating…' : '✅ Create'}
                  </button>
                  <button type="button" className="btn btn-outline btn-sm"
                    onClick={() => { setNewKbMode(false); setNewKbName(''); setNewKbDesc(''); }}>
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
            <button type="submit" className="btn btn-brand"
              disabled={uploading || newKbMode || (tab === 'file' ? !hasPending : !url.trim()) || !selectedKb}>
              {uploading
                ? '⏳ Uploading…'
                : tab === 'file' && entries.length > 1 && hasPending
                ? `⬆️ Upload ${entries.filter(e => e.status === 'pending').length} Files`
                : '⬆️ Upload & Index'}
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
