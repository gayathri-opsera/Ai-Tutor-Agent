import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { CHAT_API, KB_API, CONTENT_API } from '../../config/api';
import { useUser } from '../../auth/UserContext';
import { apiFetch } from '../../config/apiFetch';

/* ── Types ───────────────────────────────────────────────────────────────── */
interface KnowledgeBase { id: string; name: string; description: string; is_active?: boolean; }
interface Document      { id: string; title: string; status: string; chunk_count: number; content_type: string; }
interface Message       { id: string; role: 'user' | 'assistant'; content: string; sources?: { chunk_id: string; document_title: string }[]; }

function decodeTitle(raw: string): string {
  try { return decodeURIComponent(raw); } catch { return raw; }
}

const EMOJIS: Record<string, string> = { pdf: '📕', docx: '📘', text: '📄', url: '🌐', mp4: '🎬', mp3: '🎵' };
const SECTION_COLORS = ['#a435f0','#1e6055','#c0392b','#1d4ed8','#b45309'];

/* ── Progress helpers ────────────────────────────────────────────────────── */
// localStorage is the write-through cache; API is the source of truth
function getLocalProgress(kbId: string): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(`progress_${kbId}`) ?? '{}'); } catch { return {}; }
}
function setLocalProgress(kbId: string, docId: string, done: boolean) {
  const p = getLocalProgress(kbId);
  p[docId] = done;
  localStorage.setItem(`progress_${kbId}`, JSON.stringify(p));
}
async function syncProgressToServer(userId: string, kbId: string, docId: string, completed: boolean) {
  try {
    await apiFetch(`/api/v1/learner/lesson?user_id=${encodeURIComponent(userId)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kb_id: kbId, doc_id: docId, completed }),
    });
  } catch { /* best-effort */ }
}
async function fetchServerProgress(userId: string, kbId: string): Promise<string[]> {
  try {
    const r = await apiFetch(`/api/v1/learner/course/${kbId}/progress?user_id=${encodeURIComponent(userId)}`);
    if (r.ok) {
      const d = await r.json();
      return d.completed_doc_ids ?? [];
    }
  } catch { /* ignore */ }
  return [];
}

/* ── Status badge helper ─────────────────────────────────────────────────── */
function DocStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    active:     { label: '● Active',     color: '#166534', bg: '#dcfce7' },
    uploading:  { label: '⏫ Uploading', color: '#92400e', bg: '#fef9c3' },
    processing: { label: '⚙ Processing', color: '#1e40af', bg: '#dbeafe' },
    error:      { label: '✕ Error',      color: '#dc2626', bg: '#fee2e2' },
    retired:    { label: '📦 Retired',   color: '#6b7280', bg: '#f3f4f6' },
  };
  const s = map[status] ?? map['active'];
  return (
    <span style={{ fontSize: '0.65rem', fontWeight: 700, padding: '2px 7px', borderRadius: 8, color: s.color, background: s.bg }}>
      {s.label}
    </span>
  );
}

/* ── Demo data ───────────────────────────────────────────────────────────── */
const DEMO_KBS: Record<string, KnowledgeBase> = {
  'bbbbbbbb-0001-0000-0000-000000000001': { id: 'bbbbbbbb-0001-0000-0000-000000000001', name: 'Python Fundamentals', description: 'Core Python programming: variables, functions, OOP, and async patterns. Built for learners from beginner to intermediate.' },
  'bbbbbbbb-0002-0000-0000-000000000002': { id: 'bbbbbbbb-0002-0000-0000-000000000002', name: 'Machine Learning Basics', description: 'Intro to supervised, unsupervised, and reinforcement learning. Covers regression, classification, clustering, and more.' },
};
const DEMO_DOCS: Record<string, Document[]> = {
  'bbbbbbbb-0001-0000-0000-000000000001': [
    { id: 'cccccccc-0001-0000-0000-000000000001', title: 'Introduction to Python', status: 'active', chunk_count: 2, content_type: 'text' },
    { id: 'cccccccc-0002-0000-0000-000000000002', title: 'Async Programming in Python', status: 'active', chunk_count: 1, content_type: 'text' },
  ],
  'bbbbbbbb-0002-0000-0000-000000000002': [
    { id: 'cccccccc-0003-0000-0000-000000000003', title: 'Linear Regression Explained', status: 'active', chunk_count: 1, content_type: 'text' },
  ],
};
const DEMO_CONTENT: Record<string, string> = {
  'cccccccc-0001-0000-0000-000000000001': `# Introduction to Python\n\nPython is a **high-level, interpreted** programming language known for its clean, readable syntax.\n\n## Key Features\n\n- **Dynamically typed** — no variable declarations needed\n- **Multi-paradigm** — supports OOP, functional, and procedural styles\n- **Huge ecosystem** — NumPy, pandas, FastAPI, PyTorch and more\n- **Interpreted** — runs line by line, great for scripting\n\n## Your First Python Program\n\n\`\`\`python\n# Hello, World!\nprint("Hello, World!")\n\n# Variables\nname = "Alice"\nage  = 30\nprint(f"{name} is {age} years old")\n\`\`\`\n\n## Data Types\n\n| Type | Example | Description |\n|------|---------|-------------|\n| \`int\` | \`42\` | Integer numbers |\n| \`float\` | \`3.14\` | Decimal numbers |\n| \`str\` | \`"hello"\` | Text strings |\n| \`bool\` | \`True\` | Boolean values |\n| \`list\` | \`[1,2,3]\` | Ordered collection |\n| \`dict\` | \`{"a":1}\` | Key-value pairs |\n\n> **Tip**: Python infers types automatically — \`x = 42\` creates an integer without any declaration.`,
  'cccccccc-0002-0000-0000-000000000002': `# Async Programming in Python\n\nAsync programming lets you write **non-blocking I/O** code that runs efficiently in a single thread.\n\n## Core Concepts\n\n### The Event Loop\nThe event loop is the heart of async Python. It manages and schedules coroutines.\n\n### async / await\n\n\`\`\`python\nimport asyncio\nimport httpx\n\nasync def fetch_data(url: str) -> dict:\n    """Fetch JSON from a URL without blocking."""\n    async with httpx.AsyncClient() as client:\n        response = await client.get(url)\n        return response.json()\n\nasync def main():\n    data = await fetch_data("https://api.example.com/data")\n    print(data)\n\nasyncio.run(main())\n\`\`\`\n\n## When to Use Async\n\n✅ **Good for**: Web requests, database queries, file I/O\n❌ **Not for**: CPU-heavy tasks (use multiprocessing instead)\n\n## Real-World Example: This AI System\n\nThe LLM Gateway and Chat Orchestrator in this AI Tutor are built with **FastAPI + asyncio** — handling many concurrent chat requests in a single process.`,
  'cccccccc-0003-0000-0000-000000000003': `# Linear Regression Explained\n\nLinear regression is the foundation of supervised machine learning.\n\n## The Model\n\n$$y = \\beta_0 + \\beta_1 x_1 + \\beta_2 x_2 + \\ldots + \\beta_n x_n + \\varepsilon$$\n\n| Term | Meaning |\n|------|--------|\n| $y$ | Target variable (what we predict) |\n| $\\beta_0$ | Intercept |\n| $\\beta_1 \\ldots \\beta_n$ | Feature coefficients (slopes) |\n| $\\varepsilon$ | Error term |\n\n## How It Learns\n\nLinear regression minimises the **Sum of Squared Residuals (SSR)**:\n\n$$SSR = \\sum_{i=1}^{n}(y_i - \\hat{y}_i)^2$$\n\n## Python Implementation\n\n\`\`\`python\nfrom sklearn.linear_model import LinearRegression\nimport numpy as np\n\n# Training data\nX = np.array([[1], [2], [3], [4], [5]])\ny = np.array([2, 4, 5, 4, 5])\n\n# Train\nmodel = LinearRegression()\nmodel.fit(X, y)\n\n# Predict\nprediction = model.predict([[6]])\nprint(f"Predicted value: {prediction[0]:.2f}")\n\`\`\`\n\n## Key Assumptions\n\n1. **Linearity** — relationship between X and y is linear\n2. **Independence** — observations are independent\n3. **Normality** — residuals are normally distributed\n4. **Homoscedasticity** — constant variance of residuals`,
};

/* ── Video player with graceful fallback ─────────────────────────────────── */
function VideoPlayer({ docId, contentType, title }: { docId: string; contentType: string; title: string }) {
  const [mediaError, setMediaError] = useState(false);
  const mediaUrl = `${CONTENT_API}/${docId}/media`;

  if (mediaError) {
    return (
      <div style={{ marginBottom: 28, padding: '20px 24px', borderRadius: 10, background: '#fef9c3', border: '1px solid #fbbf24', display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        <span style={{ fontSize: '1.8rem', flexShrink: 0 }}>🎬</span>
        <div>
          <p style={{ fontWeight: 700, fontSize: '0.92rem', marginBottom: 4 }}>Video not available for playback</p>
          <p style={{ fontSize: '0.82rem', color: '#78350f', lineHeight: 1.5 }}>
            This video was uploaded before media storage was enabled. Please <strong>re-upload the video file</strong> to enable playback. The transcript below is still searchable.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 28, borderRadius: 10, overflow: 'hidden', background: '#000', boxShadow: '0 4px 20px rgba(0,0,0,0.15)' }}>
      <video
        key={docId}
        controls
        style={{ width: '100%', maxHeight: 420, display: 'block' }}
        preload="metadata"
        onError={() => setMediaError(true)}
      >
        <source
          src={mediaUrl}
          type={contentType === 'webm' ? 'video/webm' : 'video/mp4'}
          onError={() => setMediaError(true)}
        />
        Your browser does not support the video player.
      </video>
    </div>
  );
}

function AudioPlayer({ docId, title }: { docId: string; title: string }) {
  const [mediaError, setMediaError] = useState(false);
  const mediaUrl = `${CONTENT_API}/${docId}/media`;

  return (
    <div style={{ marginBottom: 28, padding: '16px 20px', borderRadius: 10, background: 'var(--bg)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 14 }}>
      <span style={{ fontSize: '2rem' }}>🎵</span>
      <div style={{ flex: 1 }}>
        <p style={{ fontWeight: 600, marginBottom: 6, fontSize: '0.9rem' }}>{title}</p>
        {mediaError ? (
          <p style={{ fontSize: '0.8rem', color: '#b45309', background: '#fef9c3', padding: '6px 10px', borderRadius: 6 }}>
            ⚠️ Audio not available — please re-upload the file to enable playback.
          </p>
        ) : (
          <audio
            key={docId}
            controls
            style={{ width: '100%' }}
            preload="metadata"
            onError={() => setMediaError(true)}
          >
            <source src={mediaUrl} onError={() => setMediaError(true)} />
            Your browser does not support the audio player.
          </audio>
        )}
      </div>
    </div>
  );
}


/* ── Main Component ──────────────────────────────────────────────────────── */
export function CourseDetailPage() {
  const { id: kbId = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user }  = useUser();

  const [kb, setKb]           = useState<KnowledgeBase | null>(null);
  const [docs, setDocs]       = useState<Document[]>([]);
  const [activeDoc, setActiveDoc] = useState<Document | null>(null);
  const [docContent, setDocContent] = useState<string>('');
  const [progress, setProgress] = useState<Record<string, boolean>>({});
  const [chatOpen, setChatOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const creatingSession = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const userId = user?.id ?? 'demo-user';

  /* ── Load KB + docs ────────────────────────────────────────────────────── */
  const loadKbAndDocs = async () => {
    try {
      const [kbData, docsData] = await Promise.all([
        apiFetch(`${KB_API}/${kbId}`).then(r => r.ok ? r.json() : null),
        apiFetch(`${KB_API}/${kbId}/documents`).then(r => r.ok ? r.json() : null),
      ]);
      setKb(kbData ?? DEMO_KBS[kbId] ?? null);
      const docList: Document[] = (Array.isArray(docsData?.items) ? docsData.items : Array.isArray(docsData) ? docsData : DEMO_DOCS[kbId] ?? [])
        .map((d: Document) => ({ ...d, title: decodeTitle(d.title) }));
      setDocs(docList);
      if (docList.length > 0 && !activeDoc) setActiveDoc(docList[0]);
      return docList;
    } catch {
      setKb(DEMO_KBS[kbId] ?? null);
      const docList = DEMO_DOCS[kbId] ?? [];
      setDocs(docList);
      if (docList.length > 0) setActiveDoc(docList[0]);
      return docList;
    }
  };

  useEffect(() => {
    loadKbAndDocs().then(docList => {
      // Start polling if any doc is still processing
      if (docList.some(d => d.status === 'uploading' || d.status === 'processing')) {
        startPolling();
      }
    });
    // Seed progress from localStorage first (instant), then reconcile with server
    setProgress(getLocalProgress(kbId));
    fetchServerProgress(userId, kbId).then(completedIds => {
      if (completedIds.length > 0) {
        const p: Record<string, boolean> = {};
        completedIds.forEach(id => { p[id] = true; });
        setProgress(p);
        // Persist server state back to localStorage
        localStorage.setItem(`progress_${kbId}`, JSON.stringify(p));
      }
    });
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [kbId]);

  /* ── Real-time document status polling ─────────────────────────────────── */
  const startPolling = () => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const r = await apiFetch(`${KB_API}/${kbId}/documents`);
        if (!r.ok) return;
        const d = await r.json();
        const updated: Document[] = (Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : [])
          .map((doc: Document) => ({ ...doc, title: decodeTitle(doc.title) }));
        setDocs(updated);
        // Stop polling once all docs are settled
        const allSettled = updated.every(doc => doc.status === 'active' || doc.status === 'error' || doc.status === 'retired');
        if (allSettled && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch { /* ignore */ }
    }, 3000);
  };

  /* ── Load document content ─────────────────────────────────────────────── */
  useEffect(() => {
    if (!activeDoc) return;
    apiFetch(`${CONTENT_API}/documents/${activeDoc.id}/content`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setDocContent(d?.content ?? DEMO_CONTENT[activeDoc.id] ?? ''))
      .catch(() => setDocContent(DEMO_CONTENT[activeDoc.id] ?? `# ${activeDoc.title}\n\nContent loading...`));
  }, [activeDoc]);

  /* ── Create scoped chat session ────────────────────────────────────────── */
  const createSession = useCallback(async () => {
    if (creatingSession.current || sessionId) return;
    creatingSession.current = true;
    try {
      const resp = await apiFetch(`${CHAT_API}/sessions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user?.id, knowledge_base_id: kbId }),
      });
      const data = await resp.json();
      setSessionId(data.id);
      setMessages([{ id: crypto.randomUUID(), role: 'assistant', content: `👋 Hi! Ask me anything about **${kb?.name ?? 'this course'}**. I'll search specifically within this knowledge base.` }]);
    } catch {
      const id = crypto.randomUUID();
      setSessionId(id);
      setMessages([{ id: crypto.randomUUID(), role: 'assistant', content: `👋 Hi! I'm your course assistant for **${kb?.name ?? 'this topic'}**. Ask me anything!` }]);
    } finally { creatingSession.current = false; }
  }, [kbId, kb, user, sessionId]);

  useEffect(() => { if (chatOpen && !sessionId) createSession(); }, [chatOpen, sessionId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, chatLoading]);

  /* ── Send chat message ─────────────────────────────────────────────────── */
  const sendChat = async (text?: string) => {
    const content = text ?? chatInput;
    if (!content.trim() || !sessionId || chatLoading) return;
    setChatInput('');
    setChatLoading(true);
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content };
    setMessages(m => [...m, userMsg]);
    try {
      const resp = await apiFetch(`${CHAT_API}/sessions/${sessionId}/messages`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({
          content,
          knowledge_base_id: kbId,
          // Always send at least the lesson title so the LLM stays course-scoped
          // even when docContent hasn't finished loading (e.g. first message).
          lesson_context: docContent
            ? docContent.slice(0, 6000)
            : activeDoc
            ? `Lesson title: ${activeDoc.title}\n(Full content is still loading — answer from course knowledge.)`
            : undefined,
        }),
      });
      if (!resp.ok) throw new Error();
      const reader = resp.body?.getReader();
      let acc = '';
      const aid = crypto.randomUUID();
      setMessages(m => [...m, { id: aid, role: 'assistant', content: '' }]);
      if (reader) {
        const dec = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          for (const line of dec.decode(value).split('\n')) {
            if (!line.startsWith('data:')) continue;
            try { const d = JSON.parse(line.slice(5)); if (d.token) { acc += d.token; setMessages(m => m.map(msg => msg.id === aid ? { ...msg, content: acc } : msg)); } } catch { /* ignore */ }
          }
        }
      }
    } catch {
      const q = content.toLowerCase();
      const answer = q.includes('async') ? 'Async programming uses **asyncio** with `async/await` for non-blocking I/O in Python.'
        : q.includes('python') ? 'Python is a dynamically typed, multi-paradigm language. Key strength: readable syntax and a massive ecosystem.'
        : q.includes('regression') ? 'Linear regression fits `y = β₀ + β₁x` by minimising the sum of squared residuals.'
        : `Great question about **${kb?.name}**! This topic is covered in the course documents above. Try clicking a document to read its content.`;
      setMessages(m => [...m, { id: crypto.randomUUID(), role: 'assistant', content: answer }]);
    } finally { setChatLoading(false); }
  };

  /* ── Mark document complete ────────────────────────────────────────────── */
  const toggleComplete = (docId: string) => {
    const next = !progress[docId];
    setLocalProgress(kbId, docId, next);
    setProgress({ ...progress, [docId]: next });
    syncProgressToServer(userId, kbId, docId, next);
  };

  const completed = Object.values(progress).filter(Boolean).length;
  const pct = docs.length ? Math.round((completed / docs.length) * 100) : 0;

  if (!kb) return (
    <div className="empty-state" style={{ paddingTop: 80 }}>
      <div className="empty-state-icon">⏳</div>
      <h3>Loading course…</h3>
    </div>
  );

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)', overflow: 'hidden', background: 'var(--bg)' }}>

      {/* ── Left sidebar: curriculum ──────────────────────────────────────── */}
      <aside style={{ width: 300, minWidth: 300, background: '#fff', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Course header */}
        <div style={{ padding: '16px', borderBottom: '1px solid var(--border)', background: 'var(--header-bg)', color: '#fff' }}>
          <button onClick={() => navigate('/content')}
            style={{ background: 'none', border: 'none', color: '#aaa', fontSize: '0.78rem', cursor: 'pointer', marginBottom: 8, padding: 0 }}>
            ← Back to Browse
          </button>
          <h2 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: 4, lineHeight: 1.3 }}>{kb.name}</h2>
          {/* Overall progress */}
          <div style={{ marginTop: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#aaa', marginBottom: 4 }}>
              <span>Your progress</span><span>{pct}%</span>
            </div>
            <div style={{ background: '#333', borderRadius: 4, height: 6, overflow: 'hidden' }}>
              <div style={{ background: 'var(--brand)', height: '100%', width: `${pct}%`, transition: 'width 0.5s', borderRadius: 4 }} />
            </div>
            <p style={{ fontSize: '0.7rem', color: '#888', marginTop: 4 }}>{completed}/{docs.length} lessons complete</p>
          </div>
        </div>

        {/* Section header */}
        <div style={{ padding: '10px 16px 6px', background: '#f9fafb', borderBottom: '1px solid var(--border)' }}>
          <p style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Section 1 · {docs.length} Lessons
          </p>
        </div>

        {/* Lesson list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {docs.map((doc, i) => (
            <button key={doc.id}
              onClick={() => setActiveDoc(doc)}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, width: '100%',
                padding: '12px 16px', textAlign: 'left', border: 'none',
                borderBottom: '1px solid var(--border)',
                background: activeDoc?.id === doc.id ? 'var(--brand-light)' : '#fff',
                borderLeft: activeDoc?.id === doc.id ? '3px solid var(--brand)' : '3px solid transparent',
                cursor: 'pointer', transition: 'background 0.15s',
              }}
            >
              {/* Checkbox */}
              <div onClick={e => { e.stopPropagation(); toggleComplete(doc.id); }}
                style={{
                  width: 20, height: 20, borderRadius: '50%', flexShrink: 0, marginTop: 1,
                  border: `2px solid ${progress[doc.id] ? 'var(--brand)' : 'var(--border)'}`,
                  background: progress[doc.id] ? 'var(--brand)' : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.2s',
                }}>
                {progress[doc.id] && <span style={{ color: '#fff', fontSize: '0.65rem', lineHeight: 1 }}>✓</span>}
              </div>

              <div style={{ flex: 1 }}>
                <p style={{ fontSize: '0.85rem', fontWeight: activeDoc?.id === doc.id ? 700 : 500, color: 'var(--text)', marginBottom: 2, lineHeight: 1.3 }}>
                  {EMOJIS[doc.content_type] ?? '📄'} {doc.title}
                </p>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 3 }}>
                  <span style={{ fontSize: '0.72rem', color: 'var(--muted)' }}>
                    {doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''} · {doc.content_type.toUpperCase()}
                  </span>
                  {doc.status !== 'active' && <DocStatusBadge status={doc.status} />}
                </div>
              </div>

              {/* Lesson number badge */}
              <span style={{ fontSize: '0.68rem', color: 'var(--muted)', background: 'var(--bg)', padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
                {i + 1}
              </span>
            </button>
          ))}

          {docs.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--muted)' }}>
              <p style={{ fontSize: '0.85rem' }}>No documents yet.</p>
              <button className="btn btn-brand btn-sm" style={{ marginTop: 8 }}
                onClick={() => navigate('/content/upload')}>+ Upload Document</button>
            </div>
          )}
        </div>

        {/* Chat toggle */}
        <div style={{ borderTop: '1px solid var(--border)', padding: 12 }}>
          <button
            className={`btn ${chatOpen ? 'btn-outline' : 'btn-brand'}`}
            style={{ width: '100%' }}
            onClick={() => setChatOpen(o => !o)}
          >
            {chatOpen ? '✕ Close AI Chat' : '💬 Ask AI About This Course'}
          </button>
          <button
            className="btn btn-secondary"
            style={{ width: '100%', marginTop: 8 }}
            onClick={() => navigate(`/assessment/${kbId}`)}
          >
            📝 Take Assessment
          </button>
        </div>
      </aside>

      {/* ── Main content area ─────────────────────────────────────────────── */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Top bar */}
        <div style={{ background: '#fff', borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <p style={{ fontWeight: 700, fontSize: '1rem' }}>{activeDoc?.title ?? 'Select a lesson'}</p>
            <p style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>{kb.name} · Lesson {docs.findIndex(d => d.id === activeDoc?.id) + 1} of {docs.length}</p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {activeDoc && (
              <button
                className={`btn btn-sm ${progress[activeDoc.id] ? 'btn-outline' : 'btn-brand'}`}
                onClick={() => activeDoc && toggleComplete(activeDoc.id)}
              >
                {progress[activeDoc.id] ? '✓ Completed' : 'Mark Complete'}
              </button>
            )}
            {/* Next lesson */}
            {activeDoc && docs.findIndex(d => d.id === activeDoc.id) < docs.length - 1 && (
              <button className="btn btn-brand btn-sm"
                onClick={() => {
                  const idx = docs.findIndex(d => d.id === activeDoc.id);
                  setActiveDoc(docs[idx + 1]);
                }}>
                Next Lesson →
              </button>
            )}
            {activeDoc && docs.findIndex(d => d.id === activeDoc.id) === docs.length - 1 && pct === 100 && (
              <span className="badge badge-success" style={{ padding: '6px 12px', fontSize: '0.82rem' }}>🎉 Course Complete!</span>
            )}
          </div>
        </div>

        {/* Content viewer + optional chat panel */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Document content */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px', maxWidth: chatOpen ? 'none' : 800, margin: chatOpen ? 0 : '0 auto' }}>
            {activeDoc ? (
              <article style={{ lineHeight: 1.8 }}>
                <div style={{ marginBottom: 24, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span className="badge badge-brand">{activeDoc.content_type.toUpperCase()}</span>
                  <span className="badge badge-gray">{activeDoc.chunk_count} chunk{activeDoc.chunk_count !== 1 ? 's' : ''}</span>
                  <DocStatusBadge status={activeDoc.status} />
                  {progress[activeDoc.id] && <span className="badge badge-success">✓ Completed</span>}
                  {(activeDoc.status === 'uploading' || activeDoc.status === 'processing') && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--brand)', fontStyle: 'italic' }}>
                      ⏳ Indexing — refreshing automatically…
                    </span>
                  )}
                </div>

                {/* ── Media player for video/audio lessons ──────────────────── */}
                {['mp4', 'webm'].includes(activeDoc.content_type) && activeDoc.status === 'active' && (
                  <VideoPlayer docId={activeDoc.id} contentType={activeDoc.content_type} title={activeDoc.title} />
                )}

                {['mp3', 'wav', 'ogg', 'm4a'].includes(activeDoc.content_type) && activeDoc.status === 'active' && (
                  <AudioPlayer docId={activeDoc.id} title={activeDoc.title} />
                )}

                {/* ── Transcription / text content ──────────────────────────── */}
                {['mp4', 'webm', 'mp3', 'wav', 'ogg', 'm4a'].includes(activeDoc.content_type) && docContent && (
                  <div style={{ marginBottom: 12 }}>
                    <p style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
                      📝 Transcript
                    </p>
                    <div style={{ fontSize: '0.9rem', color: 'var(--text)', background: 'var(--bg)', borderRadius: 8, padding: '14px 18px', border: '1px solid var(--border)', lineHeight: 1.7 }} className="lesson-content">
                      <ReactMarkdown>{docContent}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {!['mp4', 'webm', 'mp3', 'wav', 'ogg', 'm4a'].includes(activeDoc.content_type) && (
                  <div style={{ fontSize: '0.95rem', color: 'var(--text)' }} className="lesson-content">
                    <ReactMarkdown>{docContent}</ReactMarkdown>
                  </div>
                )}
              </article>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">📚</div>
                <h3>Select a lesson to start learning</h3>
                <p>Choose from the curriculum on the left.</p>
              </div>
            )}
          </div>

          {/* ── Scoped chat panel ──────────────────────────────────────────── */}
          {chatOpen && (
            <div style={{ width: 360, minWidth: 360, borderLeft: '1px solid var(--border)', background: '#fff', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'var(--header-bg)' }}>
                <p style={{ color: '#fff', fontWeight: 700, fontSize: '0.88rem' }}>💬 Course AI Assistant</p>
                <p style={{ color: '#aaa', fontSize: '0.72rem' }}>Answers scoped to: {kb.name}</p>
              </div>

              {/* Messages */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                {messages.map(m => (
                  <div key={m.id} style={{ display: 'flex', gap: 8, flexDirection: m.role === 'user' ? 'row-reverse' : 'row', alignItems: 'flex-start' }}>
                    <div style={{ width: 28, height: 28, borderRadius: '50%', background: m.role === 'user' ? 'var(--header-bg)' : 'var(--brand)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', flexShrink: 0 }}>
                      {m.role === 'user' ? (user?.avatar ?? '👤') : '🤖'}
                    </div>
                    <div style={{ maxWidth: '80%', padding: '10px 12px', borderRadius: 12, fontSize: '0.84rem', lineHeight: 1.6, background: m.role === 'user' ? 'var(--brand)' : 'var(--bg)', color: m.role === 'user' ? '#fff' : 'var(--text)', borderBottomRightRadius: m.role === 'user' ? 4 : 12, borderBottomLeftRadius: m.role === 'user' ? 12 : 4 }}>
                      <ReactMarkdown>{m.content || '…'}</ReactMarkdown>
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="chat-typing" style={{ padding: '10px 12px' }}><span /><span /><span /></div>
                )}
                <div ref={bottomRef} />
              </div>

              {/* Suggested questions */}
              {messages.length < 2 && (
                <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {['Explain the main concept', 'Give me a code example', 'What should I learn next?'].map(q => (
                    <button key={q} onClick={() => sendChat(q)}
                      style={{ fontSize: '0.72rem', padding: '4px 10px', background: 'var(--brand-light)', color: 'var(--brand)', border: 'none', borderRadius: 12, cursor: 'pointer', fontWeight: 600 }}>
                      {q}
                    </button>
                  ))}
                </div>
              )}

              {/* Input */}
              <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', gap: 8, background: 'var(--bg)', borderRadius: 8, padding: '6px 8px 6px 12px', border: '1px solid var(--border)' }}>
                  <input
                    style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontSize: '0.84rem' }}
                    value={chatInput} onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
                    placeholder="Ask about this course…" disabled={chatLoading}
                  />
                  <button onClick={() => sendChat()} disabled={chatLoading || !chatInput.trim()}
                    style={{ background: 'var(--brand)', color: '#fff', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 700 }}>
                    ➤
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
