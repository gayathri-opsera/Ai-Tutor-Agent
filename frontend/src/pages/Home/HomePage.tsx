import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CourseCard } from '../../components/CourseCard';

interface KB { id: string; name: string; description: string; }
interface Stats { knowledge_bases: number; documents_indexed: number; chat_sessions: number; chunks_in_vector_db: number; }

const EMOJIS = ['📚', '🤖', '🧠', '💡', '🔬', '🎯', '⚡', '🌐'];
const FEATURED_TAGS = ['Beginner Friendly', 'Popular', 'New', 'Advanced'];

export function HomePage() {
  const [kbs, setKbs] = useState<KB[]>([]);
  const [stats, setStats] = useState<Stats>({ knowledge_bases: 0, documents_indexed: 0, chat_sessions: 0, chunks_in_vector_db: 0 });
  const navigate = useNavigate();

  useEffect(() => {
    // Fetch knowledge bases
    fetch('/api/v1/knowledge-bases?organization_id=default')
      .then(r => r.json())
      .then(d => setKbs(d.items ?? d ?? []))
      .catch(() => {
        setKbs([
          { id: 'bbbbbbbb-0001-0000-0000-000000000001', name: 'Python Fundamentals', description: 'Core Python programming: variables, functions, OOP, and async patterns.' },
          { id: 'bbbbbbbb-0002-0000-0000-000000000002', name: 'Machine Learning Basics', description: 'Intro to supervised, unsupervised, and reinforcement learning.' },
        ]);
      });

    // Fetch real-time platform stats
    Promise.all([
      fetch('/api/v1/stats').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('/api/v1/analytics/summary').then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([contentStats, analyticsStats]) => {
      setStats({
        knowledge_bases: contentStats?.knowledge_bases ?? 0,
        documents_indexed: contentStats?.documents_indexed ?? 0,
        chunks_in_vector_db: contentStats?.chunks_in_vector_db ?? 0,
        chat_sessions: analyticsStats?.session_count ?? 0,
      });
    });
  }, []);

  return (
    <div>
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="hero">
        <div className="container">
          <div className="hero-inner">
            <p className="hero-eyebrow">AI-Powered Learning</p>
            <h1>Learn Anything.<br />Ask Anything.</h1>
            <p>
              Explore curated knowledge bases, get instant answers from AI,
              and track your learning progress — all in one place.
            </p>
            <div className="hero-actions">
              <button className="btn btn-brand btn-lg" onClick={() => navigate('/chat')}>
                💬 Start Chatting
              </button>
              <button className="btn btn-white btn-lg" onClick={() => navigate('/content')}>
                📚 Browse Courses
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Stats ─────────────────────────────────────────────────────────── */}
      <div className="container">
        <div className="section">
          <div className="stats-row">
            {[
              { icon: '🎓', value: stats.knowledge_bases, label: 'Knowledge Bases' },
              { icon: '📄', value: stats.documents_indexed, label: 'Documents Indexed' },
              { icon: '💬', value: stats.chat_sessions, label: 'Chat Sessions' },
              { icon: '⚡', value: stats.chunks_in_vector_db, label: 'Chunks in Vector DB' },
            ].map(s => (
              <div className="stat-card" key={s.label}>
                <div className="stat-card-icon">{s.icon}</div>
                <div className="stat-card-value">{s.value.toLocaleString()}</div>
                <div className="stat-card-label">{s.label}</div>
              </div>
            ))}
          </div>

          {/* ── Continue Learning ────────────────────────────────────────── */}
          <div className="section-header">
            <h2 className="section-title">Continue Learning</h2>
            <a href="/learning" className="section-link">View all my courses →</a>
          </div>
          <div className="cards-grid" style={{ marginBottom: 48 }}>
            {kbs.slice(0, 2).map((kb, i) => (
              <CourseCard
                key={kb.id}
                id={kb.id}
                name={kb.name}
                description={kb.description}
                emoji={EMOJIS[i % EMOJIS.length]}
                progress={i === 0 ? 65 : 20}
                docCount={i === 0 ? 2 : 1}
                rating={4.5 + i * 0.1}
                ratingCount={i === 0 ? 1240 : 820}
                tag={FEATURED_TAGS[i % FEATURED_TAGS.length]}
              />
            ))}
          </div>

          {/* ── Featured Knowledge Bases ─────────────────────────────────── */}
          <div className="section-header">
            <h2 className="section-title">Featured Knowledge Bases</h2>
            <a href="/content" className="section-link">View all →</a>
          </div>
          <div className="cards-grid">
            {kbs.map((kb, i) => (
              <CourseCard
                key={kb.id}
                id={kb.id}
                name={kb.name}
                description={kb.description}
                emoji={EMOJIS[i % EMOJIS.length]}
                docCount={i === 0 ? 2 : 1}
                rating={4.4 + (i * 0.2)}
                ratingCount={850 + i * 310}
                tag={FEATURED_TAGS[i % FEATURED_TAGS.length]}
              />
            ))}

            {/* Placeholder "coming soon" card */}
            <article className="course-card" style={{ opacity: 0.6 }}>
              <div className="course-thumb" style={{ background: 'linear-gradient(135deg,#374151 0%,#1f2937 100%)' }}>
                <span style={{ fontSize: '3rem' }}>🔜</span>
              </div>
              <div className="course-body">
                <h3 className="course-title">Deep Learning & Neural Networks</h3>
                <p className="course-instructor">Coming soon — upload your first document to get started</p>
                <div className="course-meta"><span className="course-tag">Coming Soon</span></div>
              </div>
              <div className="course-footer">
                <span className="course-doc-count">0 docs</span>
                <button className="btn btn-outline btn-sm" onClick={() => navigate('/content/upload')}>+ Upload</button>
              </div>
            </article>
          </div>
        </div>
      </div>

      {/* ── AI Banner ─────────────────────────────────────────────────────── */}
      <div style={{ background: 'linear-gradient(135deg, #1c1d1f 0%, #3b1f6e 100%)', padding: '40px 0', marginTop: 24 }}>
        <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap' }}>
          <div>
            <h2 style={{ color: '#fff', fontSize: '1.4rem', fontWeight: 800, marginBottom: 8 }}>
              🤖 AI-Powered Answers
            </h2>
            <p style={{ color: '#aaa', fontSize: '0.9rem', maxWidth: 480 }}>
              Ask questions in natural language. Our RAG pipeline retrieves the most relevant document
              chunks and generates accurate, sourced answers.
            </p>
          </div>
          <button className="btn btn-brand btn-lg" onClick={() => navigate('/chat')}>
            Try the AI Chat →
          </button>
        </div>
      </div>
    </div>
  );
}
