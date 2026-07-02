import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { CHAT_API, KB_API } from '../config/api';
import { useUser } from '../auth/UserContext';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{ chunk_id: string; document_title: string }>;
  rating?: 'up' | 'down';
  confidence?: number;
  source_type?: 'documents' | 'ai_knowledge';
}

interface Session { id: string; title: string; }
interface KnowledgeBase { id: string; name: string; }

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
  const bottomRef    = useRef<HTMLDivElement>(null);
  const creatingRef  = useRef(false); // guard against double-creation

  const scrollToBottom = () => bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(scrollToBottom, [messages, loading]);

  // Fetch available knowledge bases
  useEffect(() => {
    fetch(KB_API)
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

  // Load saved sessions from the server when user is known
  useEffect(() => {
    if (!user?.id) return;
    fetch(`${CHAT_API}/sessions?user_id=${encodeURIComponent(user.id)}`)
      .then(r => r.ok ? r.json() : { sessions: [] })
      .then((data: { sessions: Session[] }) => {
        if (data.sessions?.length) {
          setSessions(data.sessions);
        }
      })
      .catch(() => {});
  }, [user?.id]);

  const createSession = useCallback(async (kbId?: string) => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    const useKbId = (kbId && kbId !== '__none__') ? kbId : (selectedKbId !== '__none__' ? selectedKbId : undefined);
    try {
      const resp = await fetch(`${CHAT_API}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user?.id ?? 'demo-user', knowledge_base_id: useKbId || undefined }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: { id: string; title?: string } = await resp.json();
      const title = data.title || 'New Chat';
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
      const resp = await fetch(`${CHAT_API}/sessions/${s.id}/history`);
      if (resp.ok) {
        const data: { messages: Array<{ role: string; content: string; sources?: unknown[] }> } = await resp.json();
        if (data.messages?.length) {
          setMessages(data.messages.map(m => ({
            id: crypto.randomUUID(),
            role: m.role as 'user' | 'assistant',
            content: m.content,
            sources: m.sources as Message['sources'],
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
      const resp = await fetch(`${CHAT_API}/sessions/${activeSession}/messages`, {
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
              if (data.sources) sources.push(...(data.sources as Message['sources'] ?? []));
              if (data.source_type) source_type = data.source_type;
              if (data.confidence_score !== undefined) confidence = data.confidence_score;
            } catch { /* ignore SSE parse errors */ }
          }
        }
      }
      setMessages(m => m.map(msg =>
        msg.id === assistantId ? { ...msg, sources, confidence, source_type } : msg
      ));
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

  const rateMessage = (id: string, rating: 'up' | 'down') => {
    setMessages(msgs => msgs.map(m => m.id === id ? { ...m, rating } : m));
    // Track rating in analytics
    fetch('/api/v1/analytics/events', {
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
          <p className="chat-sidebar-subtitle">{user?.role}</p>
        </div>

        <button className="chat-new-btn" onClick={() => createSession(selectedKbId === '__none__' ? undefined : selectedKbId)}>+ New Chat</button>

        <ul className="chat-sessions-list" role="list">
          {sessions.map(s => (
            <li key={s.id}>
              <button
                className={`chat-session-item${activeSession === s.id ? ' active' : ''}`}
                onClick={() => selectSession(s)}
              >
                <span className="chat-session-icon">💬</span>
                {s.title}
              </button>
            </li>
          ))}
        </ul>

        {/* Starter prompts */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid #333' }}>
          <p style={{ fontSize: '0.7rem', color: '#888', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Suggested questions
          </p>
          {STARTER_PROMPTS.map(q => (
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
            {/* Knowledge base selector */}
            {knowledgeBases.length > 0 ? (
              <select
                value={selectedKbId}
                onChange={e => setSelectedKbId(e.target.value)}
                style={{ fontSize: '0.8rem', background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', outline: 'none' }}
                title="Select knowledge base for RAG"
              >
                <option value="">🌐 All knowledge (no RAG filter)</option>
                {knowledgeBases.map(kb => (
                  <option key={kb.id} value={kb.id}>📚 {kb.name}</option>
                ))}
              </select>
            ) : (
              <p className="chat-topbar-meta">Loading knowledge bases…</p>
            )}
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
