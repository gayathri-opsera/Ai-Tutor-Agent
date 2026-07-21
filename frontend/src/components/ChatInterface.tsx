import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { CHAT_API, KB_API } from '../config/api';
import { useUser } from '../auth/UserContext';
import { apiFetch } from '../config/apiFetch';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{
    chunk_id: string;
    document_id?: string;
    document_title: string;
    score?: number;
    excerpt?: string;
  }>;
  rating?: 'up' | 'down';
  confidence?: number;
  source_type?: 'documents' | 'ai_knowledge';
}

interface Session { id: string; title: string; created_at?: string; }
interface KnowledgeBase { id: string; name: string; }

// Persist anonymous session IDs in localStorage so they survive page reloads
const LS_KEY = 'ai_tutor_session_ids';
function localSessionIds(): string[] {
  try { return JSON.parse(localStorage.getItem(LS_KEY) ?? '[]'); } catch { return []; }
}
function addLocalSessionId(id: string) {
  const ids = localSessionIds();
  if (!ids.includes(id)) localStorage.setItem(LS_KEY, JSON.stringify([id, ...ids].slice(0, 50)));
}

const STARTER_PROMPTS = [
  'What is Python and why is it popular?',
  'Explain async/await with an example',
  'What is linear regression?',
  'How does RAG work in this system?',
];

export function ChatInterface() {
  const { user } = useUser();
  const [sessions, setSessions]           = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [messages, setMessages]           = useState<Message[]>([]);
  const [input, setInput]                 = useState('');
  const [loading, setLoading]             = useState(false);
  const [error, setError]                 = useState<string | null>(null);
  const [activeTitle, setActiveTitle]     = useState('New Chat');
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId]   = useState<string>('');
  // Rename state — which session is being edited inline
  const [renamingId, setRenamingId]       = useState<string | null>(null);
  const [renameValue, setRenameValue]     = useState('');
  const [deletingId, setDeletingId]       = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const bottomRef    = useRef<HTMLDivElement>(null);
  const creatingRef  = useRef(false); // guard against double-creation

  const scrollToBottom = () => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); };
  useEffect(scrollToBottom, [messages, loading]);

  // Fetch available knowledge bases
  useEffect(() => {
    apiFetch(KB_API)
      .then(r => r.ok ? r.json() : null)
      .then((data: { items?: KnowledgeBase[] } | KnowledgeBase[] | null) => {
        // API returns { items: [...] }; handle both shapes defensively
        const list: KnowledgeBase[] = Array.isArray(data)
          ? data
          : (data as { items?: KnowledgeBase[] })?.items ?? [];
        if (list.length > 0) {
          setKnowledgeBases(list);
          setSelectedKbId(list[0].id);
        } else {
          // No KBs yet — still start a session without RAG filter
          setKnowledgeBases([]);
          setSelectedKbId('__none__'); // sentinel to trigger session creation
        }
      })
      .catch(() => {
        setSelectedKbId('__none__'); // backend unreachable — still create demo session
      });
  }, []);

  // Suggested questions come from STARTER_PROMPTS; the /api/internal/rag endpoint
  // is service-to-service only (requires X-Service-Token) so we don't call it from the browser.
  useEffect(() => {
    setSuggestedQuestions([]);
  }, [selectedKbId]);

  // Load saved sessions — server for authenticated users, localStorage IDs for anonymous
  useEffect(() => {
    const userId = user?.id;
    if (userId) {
      // Authenticated: load all sessions from the server
      apiFetch(`${CHAT_API}/sessions?user_id=${encodeURIComponent(userId)}`)
        .then(r => r.ok ? r.json() : { sessions: [] })
        .then((data: { sessions: Session[] }) => {
          if (data.sessions?.length) setSessions(data.sessions);
        })
        .catch(() => {});
    } else {
      // Anonymous: fetch individual sessions by ID stored in localStorage
      const ids = localSessionIds();
      if (!ids.length) return;
      Promise.allSettled(
        ids.map(id =>
          apiFetch(`${CHAT_API}/sessions/${id}/history`)
            .then(r => r.ok ? r.json().then(() => id) : null)
            .catch(() => null)
        )
      ).then(results => {
        const validIds = results
          .filter(r => r.status === 'fulfilled' && r.value)
          .map(r => (r as PromiseFulfilledResult<string>).value);
        if (validIds.length) {
          // We only have IDs, not titles — create minimal session objects with stored titles
          const stored: Session[] = validIds.map(id => ({
            id,
            title: (JSON.parse(localStorage.getItem(`session_title_${id}`) ?? '"New Chat"') as string),
          }));
          setSessions(stored);
        }
      });
    }
  }, [user?.id]);

  const createSession = useCallback(async (kbId?: string) => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    const useKbId = (kbId && kbId !== '__none__') ? kbId : (selectedKbId !== '__none__' ? selectedKbId : undefined);
    try {
      const resp = await apiFetch(`${CHAT_API}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user?.id ?? 'demo-user', knowledge_base_id: useKbId || undefined }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: { id: string; title?: string } = await resp.json();
      const title = data.title || 'New Chat';
      addLocalSessionId(data.id);
      localStorage.setItem(`session_title_${data.id}`, JSON.stringify(title));
      setSessions(s => [{ id: data.id, title }, ...s.filter(x => x.id !== data.id)]);
      setActiveSession(data.id);
      setActiveTitle(title);
      const kbName = knowledgeBases.find(kb => kb.id === useKbId)?.name;
      setMessages([{
        id: crypto.randomUUID(), role: 'assistant',
        content: `👋 Hi **${user?.name ?? 'there'}**! I'm your AI Tutor.${kbName ? `\n\nI'm searching the **${kbName}** knowledge base for your answers.` : '\n\nAsk me anything about your knowledge bases — Python, Machine Learning, or any uploaded content!'}`,
      }]);
    } catch {
      // Offline / backend unavailable — create a local demo session
      const id = crypto.randomUUID();
      const title = `Chat — ${user?.name?.split(' ')[0] ?? 'Demo'}`;
      setSessions(s => [{ id, title }, ...s]);
      setActiveSession(id);
      setActiveTitle(title);
      setMessages([{
        id: crypto.randomUUID(), role: 'assistant',
        content: `👋 Hi **${user?.name ?? 'there'}**! I'm your AI Tutor.\n\n⚠️ The chat backend is warming up — I'm running in **demo mode** for now. Try one of the starter prompts below!`,
      }]);
    } finally {
      creatingRef.current = false;
    }
  }, [user, selectedKbId, knowledgeBases]);

  // Create a session once KB list has loaded (or failed to load)
  const initialSessionCreated = useRef(false);
  useEffect(() => {
    if (!initialSessionCreated.current && selectedKbId) {
      initialSessionCreated.current = true;
      createSession(selectedKbId === '__none__' ? undefined : selectedKbId);
    }
  }, [selectedKbId]);

  const selectSession = async (s: Session) => {
    setActiveSession(s.id);
    setActiveTitle(s.title);
    setMessages([]);
    // Load saved messages from server
    try {
      const resp = await apiFetch(`${CHAT_API}/sessions/${s.id}/history`);
      if (resp.ok) {
        const data: { messages: Array<{ role: string; content: string; sources?: unknown[] }> } = await resp.json();
        if (data.messages?.length) {
          setMessages(data.messages.map(m => ({
            id: crypto.randomUUID(),
            role: m.role as 'user' | 'assistant',
            content: m.content,
            sources: Array.isArray(m.sources) ? m.sources as Message['sources'] : [],
          })));
        }
      }
    } catch { /* silently keep empty state */ }
  };

  const sendMessage = async (text?: string) => {
    const content = text ?? input;
    if (!content.trim() || !activeSession || loading) return;
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content };
    setMessages(m => [...m, userMsg]);
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const resp = await apiFetch(`${CHAT_API}/sessions/${activeSession}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ content, knowledge_base_id: (selectedKbId && selectedKbId !== '__none__') ? selectedKbId : undefined }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body?.getReader();
      let assistantContent = '';
      const sources: Message['sources'] = [];
      let confidence: number | undefined;
      let source_type: 'documents' | 'ai_knowledge' | undefined;
      const assistantId = crypto.randomUUID();
      setMessages(m => [...m, { id: assistantId, role: 'assistant', content: '' }]);

      if (reader) {
        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          for (const line of decoder.decode(value).split('\n')) {
            if (!line.startsWith('data:')) continue;
            try {
              const data = JSON.parse(line.slice(5).trim());
              if (data.token) {
                assistantContent += data.token;
                setMessages(m => m.map(msg =>
                  msg.id === assistantId ? { ...msg, content: assistantContent } : msg
                ));
              }
              if (data.sources && Array.isArray(data.sources)) sources.push(...(data.sources as Message['sources'] ?? []));
              if (data.source_type) source_type = data.source_type;
              if (data.confidence_score !== undefined) confidence = data.confidence_score;
            } catch { /* ignore SSE parse errors */ }
          }
        }
      }
      setMessages(m => m.map(msg =>
        msg.id === assistantId ? { ...msg, sources, confidence, source_type } : msg
      ));
      // Sync auto-generated title after first message
      const msgCount = messages.filter(m => m.role === 'user').length;
      if (msgCount === 0 && activeSession) syncTitle(activeSession);
    } catch {
      const demo = getDemoAnswer(content);
      setMessages(m => [...m, {
        id: crypto.randomUUID(), role: 'assistant',
        content: demo.text,
        sources: [],
        source_type: 'ai_knowledge' as const,
      }]);
    } finally {
      setLoading(false);
    }
  };

  // After first message, sync the auto-generated title from the server
  const syncTitle = useCallback(async (sessionId: string) => {
    try {
      const r = await apiFetch(`${CHAT_API}/sessions?user_id=${encodeURIComponent(user?.id ?? 'demo-user')}`);
      if (!r.ok) return;
      const data: { sessions: Session[] } = await r.json();
      const updated = data.sessions.find(s => s.id === sessionId);
      if (updated && updated.title !== 'New Chat') {
        setSessions(s => s.map(x => x.id === sessionId ? { ...x, title: updated.title } : x));
        setActiveTitle(updated.title);
        localStorage.setItem(`session_title_${sessionId}`, JSON.stringify(updated.title));
      }
    } catch { /* best-effort */ }
  }, [user?.id]);

  const renameSession = useCallback(async (sessionId: string, newTitle: string) => {
    const title = newTitle.trim();
    if (!title) return;
    // Optimistic update
    setSessions(s => s.map(x => x.id === sessionId ? { ...x, title } : x));
    if (sessionId === activeSession) setActiveTitle(title);
    localStorage.setItem(`session_title_${sessionId}`, JSON.stringify(title));
    // Persist to server
    await apiFetch(`${CHAT_API}/sessions/${sessionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).catch(() => {});
  }, [activeSession]);

  const deleteSession = useCallback(async (sessionId: string) => {
    setDeletingId(sessionId);
    try {
      await apiFetch(`${CHAT_API}/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {});
      setSessions(s => s.filter(x => x.id !== sessionId));
      if (activeSession === sessionId) {
        setActiveSession(null);
        setMessages([]);
        setActiveTitle('New Chat');
      }
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  }, [activeSession]);

  const rateMessage = (id: string, rating: 'up' | 'down') => {
    setMessages(msgs => msgs.map(m => m.id === id ? { ...m, rating } : m));
    // Track rating in analytics
    apiFetch('/api/v1/analytics/events', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: 'answer.rated',
        user_id: user?.id ?? 'demo-user',
        rating: rating === 'up' ? 5 : 1,
        metadata: { message_id: id },
      }),
    }).catch(() => {});
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const selectedKbName = knowledgeBases.find(kb => kb.id === selectedKbId)?.name;

  return (
    <div className="chat-shell">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className="chat-sidebar">
        <div className="chat-sidebar-header">
          <p className="chat-sidebar-title">💬 AI Tutor Chat</p>
          <p className="chat-sidebar-subtitle">{user?.roles?.[0]}</p>
        </div>

        <button className="chat-new-btn" onClick={() => createSession(selectedKbId === '__none__' ? undefined : selectedKbId)}>+ New Chat</button>

        <ul className="chat-sessions-list" role="list">
          {(() => {
            const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
            const recentSessions = sessions.filter(s =>
              !s.created_at || new Date(s.created_at).getTime() >= sevenDaysAgo
            );
            if (recentSessions.length === 0) {
              return (
                <li style={{ padding: '16px', color: '#666', fontSize: '0.8rem', textAlign: 'center', lineHeight: 1.5 }}>
                  <span style={{ display: 'block', fontSize: '1.5rem', marginBottom: 6 }}>💬</span>
                  No chats in the last 7 days.<br />Start a new chat above!
                </li>
              );
            }
            return recentSessions.map(s => (
              <li key={s.id} style={{ position: 'relative' }}>
                {renamingId === s.id ? (
                  /* ── Inline rename input ── */
                  <div style={{ display: 'flex', gap: 4, padding: '4px 8px' }}>
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={e => setRenameValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') { renameSession(s.id, renameValue); setRenamingId(null); }
                        if (e.key === 'Escape') setRenamingId(null);
                      }}
                      onBlur={() => { renameSession(s.id, renameValue); setRenamingId(null); }}
                      style={{ flex: 1, fontSize: '0.8rem', padding: '4px 6px', borderRadius: 4, border: '1px solid #7c3aed', background: '#1a1a2e', color: '#fff', outline: 'none' }}
                      maxLength={80}
                    />
                  </div>
                ) : confirmDeleteId === s.id ? (
                  /* ── Delete confirmation ── */
                  <div style={{ padding: '8px 12px', background: '#1a0a0a', borderLeft: '3px solid #ef4444' }}>
                    <p style={{ fontSize: '0.75rem', color: '#fca5a5', marginBottom: 6 }}>
                      Delete this chat?
                    </p>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => deleteSession(s.id)}
                        disabled={deletingId === s.id}
                        style={{ flex: 1, background: '#ef4444', color: '#fff', border: 'none',
                                 padding: '3px 8px', borderRadius: 4, cursor: 'pointer', fontSize: '0.75rem' }}>
                        {deletingId === s.id ? '…' : 'Delete'}
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(null)}
                        style={{ flex: 1, background: '#333', color: '#ccc', border: 'none',
                                 padding: '3px 8px', borderRadius: 4, cursor: 'pointer', fontSize: '0.75rem' }}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  /* ── Normal session row ── */
                  <button
                    className={`chat-session-item${activeSession === s.id ? ' active' : ''}`}
                    onClick={() => selectSession(s)}
                    title="Double-click to rename"
                    onDoubleClick={e => {
                      e.stopPropagation();
                      setRenamingId(s.id);
                      setRenameValue(s.title);
                    }}
                    style={{ paddingRight: 32 }}
                  >
                    <span className="chat-session-icon">💬</span>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                      {s.title}
                    </span>
                    <button
                      onClick={e => { e.stopPropagation(); setConfirmDeleteId(s.id); }}
                      style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
                               background: 'none', border: 'none', color: '#555', cursor: 'pointer',
                               fontSize: '0.8rem', padding: '2px 4px', borderRadius: 3 }}
                      title="Delete session"
                      onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
                      onMouseLeave={e => (e.currentTarget.style.color = '#555')}
                      aria-label="Delete session"
                    >
                      🗑
                    </button>
                  </button>
                )}
              </li>
            ));
          })()}
        </ul>

        {/* Starter / suggested prompts */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid #333' }}>
          <p style={{ fontSize: '0.7rem', color: '#888', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Suggested questions
          </p>
          {(suggestedQuestions.length > 0 ? suggestedQuestions : STARTER_PROMPTS).map(q => (
            <button key={q} onClick={() => sendMessage(q)}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '5px 0', background: 'transparent', border: 'none', color: '#999', fontSize: '0.75rem', cursor: 'pointer', lineHeight: 1.4 }}
              onMouseEnter={e => (e.currentTarget.style.color = '#fff')}
              onMouseLeave={e => (e.currentTarget.style.color = '#999')}
            >
              → {q}
            </button>
          ))}
        </div>
      </aside>

      {/* ── Main ────────────────────────────────────────────────────────── */}
      <main className="chat-main">
        {/* Top bar */}
        <div className="chat-topbar">
          <div>
            <p className="chat-topbar-title">{activeTitle}</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 2, flexWrap: 'wrap' }}>
              {/* User context pill */}
              <span style={{ fontSize: '0.75rem', color: '#a78bfa', fontWeight: 500 }}>
                👤 {user?.name ?? 'Guest'}
              </span>
              <span style={{ color: '#444', fontSize: '0.7rem' }}>·</span>
              {/* KB selector inline */}
              {knowledgeBases.length > 0 ? (
                <select
                  value={selectedKbId}
                  onChange={e => setSelectedKbId(e.target.value)}
                  style={{ fontSize: '0.75rem', background: 'transparent', border: 'none',
                           color: selectedKbId && selectedKbId !== '__none__' ? '#67e8f9' : 'var(--muted)',
                           cursor: 'pointer', outline: 'none', fontWeight: 500 }}
                  title="Select knowledge base for RAG"
                >
                  <option value="">🌐 All knowledge (no RAG filter)</option>
                  {knowledgeBases.map(kb => (
                    <option key={kb.id} value={kb.id}>📚 {kb.name}</option>
                  ))}
                </select>
              ) : (
                <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Loading courses…</span>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <span className="badge badge-success">● AI Active</span>
            <span className="badge badge-brand">{selectedKbName ? `📚 ${selectedKbName}` : 'RAG Enabled'}</span>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="error-banner" role="alert" style={{ margin: '8px 20px' }}>
            ⚠️ {error}
            <button onClick={() => setError(null)} style={{ marginLeft: 12, fontWeight: 600 }}>✕</button>
          </div>
        )}

        {/* Messages */}
        <div className="chat-messages" role="log" aria-live="polite">
          {messages.map(m => (
            <div key={m.id} className={`chat-bubble-row${m.role === 'user' ? ' user' : ''}`}>
              <div className={`chat-avatar ${m.role === 'user' ? 'user' : 'ai'}`}>
                {m.role === 'user' ? (user?.avatar ?? '👤') : '🤖'}
              </div>
              <div style={{ maxWidth: '72%' }}>
                {/* Sender name + course context label */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3,
                              justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                  <span style={{ fontSize: '0.7rem', fontWeight: 600,
                                 color: m.role === 'user' ? '#a78bfa' : '#67e8f9' }}>
                    {m.role === 'user' ? (user?.name ?? 'You') : 'AI Tutor'}
                  </span>
                  {m.role === 'user' && selectedKbName && (
                    <span style={{ fontSize: '0.65rem', background: 'rgba(103,232,249,0.12)',
                                   color: '#67e8f9', border: '1px solid rgba(103,232,249,0.25)',
                                   borderRadius: 10, padding: '1px 6px' }}>
                      📚 {selectedKbName}
                    </span>
                  )}
                </div>
                <div className={`chat-bubble ${m.role === 'user' ? 'user' : 'ai'}`}>
                  <ReactMarkdown>{m.content || '…'}</ReactMarkdown>
                </div>
                {m.role === 'assistant' && m.content && (
                  <div className="chat-rating">
                    <button className={`chat-rate-btn${m.rating === 'up' ? ' active' : ''}`}
                      onClick={() => rateMessage(m.id, 'up')} aria-label="Helpful">👍</button>
                    <button className={`chat-rate-btn${m.rating === 'down' ? ' active' : ''}`}
                      onClick={() => rateMessage(m.id, 'down')} aria-label="Not helpful">👎</button>
                  </div>
                )}
                {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                  <div style={{ marginTop: 6, padding: '6px 10px', background: 'rgba(255,255,255,0.04)',
                                border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6 }}>
                    <p style={{ fontSize: '0.68rem', color: '#888', marginBottom: 4,
                                textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 600 }}>
                      📄 Sources
                    </p>
                    {m.sources.map((src, i) => (
                      <div key={src.chunk_id || i}
                        style={{ fontSize: '0.75rem', color: '#bbb', padding: '2px 0',
                                 borderTop: i > 0 ? '1px solid rgba(255,255,255,0.06)' : 'none',
                                 paddingTop: i > 0 ? 4 : 2 }}>
                        <span style={{ fontWeight: 600, color: '#a0c4ff' }}>{src.document_title}</span>
                        {src.score !== undefined && (
                          <span style={{ marginLeft: 6, fontSize: '0.68rem', color: '#666' }}>
                            ({Math.round(src.score * 100)}%)
                          </span>
                        )}
                        {src.excerpt && (
                          <p style={{ margin: '2px 0 0', color: '#777', fontSize: '0.7rem',
                                      overflow: 'hidden', textOverflow: 'ellipsis',
                                      display: '-webkit-box', WebkitLineClamp: 2,
                                      WebkitBoxOrient: 'vertical' }}>
                            {src.excerpt}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="chat-bubble-row">
              <div className="chat-avatar ai">🤖</div>
              <div className="chat-typing"><span /><span /><span /></div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="chat-input-area">
          <div className="chat-input-row">
            <textarea
              className="chat-input" value={input}
              onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
              placeholder="Ask anything… (Enter to send, Shift+Enter for new line)"
              disabled={loading} rows={1} aria-label="Message input"
            />
            <button className="chat-send-btn"
              onClick={() => sendMessage()} disabled={loading || !input.trim()}
              aria-label="Send">
              ➤
            </button>
          </div>
          <p className="chat-input-hint">
            🔒 PII auto-redacted · RAG-grounded answers
          </p>
        </div>
      </main>
    </div>
  );
}

/* ── Demo answers (used when backend is unavailable) ─────────────────────── */
function getDemoAnswer(q: string): { text: string; sources: Message['sources'] } {
  const lq = q.toLowerCase();
  if (lq.includes('python') || lq.includes('popular'))
    return { text: "**Python** is a high-level interpreted language celebrated for:\n\n- **Readable syntax** — close to English, easy to learn\n- **Dynamic typing** — no declaration needed\n- **Multi-paradigm** — OOP, functional, procedural\n- **Huge ecosystem** — NumPy, FastAPI, PyTorch, pandas\n\nIt's the #1 language for data science, AI/ML, and scripting worldwide.", sources: [{ chunk_id: '1', document_title: 'Introduction to Python' }] };
  if (lq.includes('async') || lq.includes('await') || lq.includes('asyncio'))
    return { text: "**async/await** in Python enables non-blocking I/O:\n\n```python\nasync def fetch(url: str) -> dict:\n    async with httpx.AsyncClient() as client:\n        return (await client.get(url)).json()\n```\n\n`asyncio` runs coroutines concurrently in one thread using an **event loop** — no threads needed.", sources: [{ chunk_id: '2', document_title: 'Async Programming in Python' }] };
  if (lq.includes('linear') || lq.includes('regression'))
    return { text: "**Linear regression** fits a line to data:\n\n`y = β₀ + β₁x₁ + … + βₙxₙ + ε`\n\n| Term | Meaning |\n|------|--------|\n| β₀ | Intercept |\n| β₁…n | Feature weights |\n| ε | Error term |\n\nMinimises **sum of squared residuals** (OLS) to find the best-fit line.", sources: [{ chunk_id: '3', document_title: 'Linear Regression Explained' }] };
  if (lq.includes('rag') || lq.includes('retrieval'))
    return { text: "**RAG (Retrieval-Augmented Generation)** in this system:\n\n1. 📄 **Ingest** — Documents chunked & embedded → Weaviate vector DB\n2. 🔍 **Retrieve** — Query embedded → top-K chunks retrieved by cosine similarity\n3. 🤖 **Generate** — The AI reads chunks + question → grounded answer with citations\n\nThis prevents hallucinations and keeps answers up-to-date with your documents.", sources: [] };
  return { text: "Great question! I'm searching the knowledge base… For the best results, try asking about **Python**, **async programming**, **linear regression**, or **how RAG works** in this system.", sources: [] };
}
