import { useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{ chunk_id: string; document_title: string }>;
  rating?: 'up' | 'down';
}

export interface ChatInterfaceProps {
  apiBase?: string;
}

export function ChatInterface({ apiBase = '/api/v1/chat' }: ChatInterfaceProps) {
  const [sessions, setSessions] = useState<Array<{ id: string; title: string }>>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createSession = useCallback(async () => {
    const resp = await fetch(`${apiBase}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'demo-user' }),
    });
    const data = await resp.json();
    setSessions((s) => [...s, { id: data.id, title: data.title || 'New Chat' }]);
    setActiveSession(data.id);
  }, [apiBase]);

  useEffect(() => {
    if (!activeSession && sessions.length === 0) createSession();
  }, [activeSession, sessions.length, createSession]);

  const sendMessage = async () => {
    if (!input.trim() || !activeSession) return;
    setLoading(true);
    setError(null);
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: input };
    setMessages((m) => [...m, userMsg]);
    setInput('');
    try {
      const resp = await fetch(`${apiBase}/sessions/${activeSession}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ content: userMsg.content }),
      });
      if (!resp.ok) throw new Error('Failed to send message');
      const reader = resp.body?.getReader();
      let assistantContent = '';
      const sources: Message['sources'] = [];
      if (reader) {
        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value);
          for (const line of chunk.split('\n')) {
            if (line.startsWith('data:')) {
              try {
                const data = JSON.parse(line.slice(5).trim());
                if (data.token) assistantContent += data.token;
                if (data.sources) sources.push(...data.sources);
              } catch { /* ignore parse errors */ }
            }
          }
        }
      }
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'assistant', content: assistantContent || 'Response received.', sources }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const rateMessage = (id: string, rating: 'up' | 'down') => {
    setMessages((msgs) => msgs.map((m) => (m.id === id ? { ...m, rating } : m)));
  };

  return (
    <div className="app-layout" aria-label="Chat interface">
      <aside className="sidebar" aria-label="Session list">
        <h2>Sessions</h2>
        <button type="button" onClick={createSession} aria-label="New chat session">+ New Chat</button>
        <ul role="list">
          {sessions.map((s) => (
            <li key={s.id}>
              <button type="button" onClick={() => setActiveSession(s.id)} aria-current={activeSession === s.id}>{s.title}</button>
            </li>
          ))}
        </ul>
      </aside>
      <main className="main">
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">Retry</button>
          </div>
        )}
        <div role="log" aria-live="polite" aria-label="Chat messages">
          {messages.map((m) => (
            <article key={m.id} aria-label={`${m.role} message`}>
              <ReactMarkdown>{m.content}</ReactMarkdown>
              {m.sources?.map((s) => (
                <a key={s.chunk_id} href={`#source-${s.chunk_id}`} aria-label={`Source: ${s.document_title}`}>
                  [{s.document_title}]
                </a>
              ))}
              {m.role === 'assistant' && (
                <div role="group" aria-label="Rate this message">
                  <button type="button" aria-label="Thumbs up" onClick={() => rateMessage(m.id, 'up')}>👍</button>
                  <button type="button" aria-label="Thumbs down" onClick={() => rateMessage(m.id, 'down')}>👎</button>
                </div>
              )}
            </article>
          ))}
          {loading && <div aria-label="Assistant is typing">Typing...</div>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); sendMessage(); }} aria-label="Send message form">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Message input"
            disabled={loading}
          />
          <button type="submit" disabled={loading || !input.trim()} aria-label="Send message">Send</button>
        </form>
      </main>
    </div>
  );
}
