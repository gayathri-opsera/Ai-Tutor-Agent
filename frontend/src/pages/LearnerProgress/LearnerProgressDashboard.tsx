import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from 'recharts';
import { useUser } from '../../auth/UserContext';

const LEARNER_API = '/api/v1/learner';
const ANALYTICS_API = '/api/v1/analytics';

interface TopicProgress { topic: string; status: string; score: number; question_count: number; }
interface LearnerProfile {
  user_id: string; display_name: string; proficiency_level: string;
  total_sessions: number; total_queries: number;
  mastered: string[]; in_progress: string[]; not_started: string[];
  topics: TopicProgress[];
}
interface AnalyticsSummary { session_count: number; query_volume: number; average_rating: number; topic_distribution: Record<string,number>; }

const LEVEL_COLORS: Record<string, string> = { mastered: '#22c55e', in_progress: '#f59e0b', not_started: '#94a3b8' };

export function LearnerProgressDashboard() {
  const { user } = useUser();
  const [profile, setProfile]     = useState<LearnerProfile | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading]     = useState(true);

  const userId = user?.id ?? 'demo-user';

  useEffect(() => {
    Promise.all([
      fetch(`${LEARNER_API}/progress?user_id=${userId}`).then(r => r.ok ? r.json() : null),
      fetch(`${ANALYTICS_API}/summary`).then(r => r.ok ? r.json() : null),
    ]).then(([p, a]) => {
      if (p) setProfile(p);
      if (a) setAnalytics(a);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [userId]);

  const topicData = (profile?.topics ?? []).map(t => ({
    topic: t.topic.length > 16 ? t.topic.slice(0, 14) + '…' : t.topic,
    mastery: Math.round(t.score * 100),
    status: t.status,
  }));

  const topicDistData = analytics
    ? Object.entries(analytics.topic_distribution).slice(0, 7).map(([t, c]) => ({ topic: t.slice(0,16), queries: c }))
    : [];

  const achievements = [
    { emoji: '🚀', label: 'First Query',    earned: (profile?.total_queries ?? 0) >= 1 },
    { emoji: '💬', label: '10 Questions',   earned: (profile?.total_queries ?? 0) >= 10 },
    { emoji: '📚', label: '3 Sessions',     earned: (profile?.total_sessions ?? 0) >= 3 },
    { emoji: '🎯', label: 'Topic Master',   earned: (profile?.mastered ?? []).length >= 1 },
    { emoji: '💡', label: '50 Questions',   earned: (profile?.total_queries ?? 0) >= 50 },
    { emoji: '🏆', label: 'Course Complete', earned: (profile?.mastered ?? []).length >= 5 },
  ];

  if (loading) {
    return (
      <div className="container" style={{ paddingTop: 60, textAlign: 'center' }}>
        <div className="spinner" />
        <p className="text-muted mt-4">Loading your progress…</p>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div className="container">
          <h1>My Learning Progress</h1>
          <p>Track your mastery across all knowledge bases</p>
        </div>
      </div>

      <div className="container">
        <div className="section">
          {/* Stats row */}
          <div className="stats-row">
            {[
              { icon: '💬', value: String(profile?.total_queries ?? 0), label: 'Total queries' },
              { icon: '📚', value: String(profile?.total_sessions ?? 0), label: 'Sessions' },
              { icon: '🎯', value: String(profile?.mastered?.length ?? 0), label: 'Topics mastered' },
              { icon: '⭐', value: profile?.proficiency_level ?? 'beginner', label: 'Level' },
            ].map(s => (
              <div className="stat-card" key={s.label}>
                <div className="stat-card-icon">{s.icon}</div>
                <div className="stat-card-value" style={{ textTransform: 'capitalize' }}>{s.value}</div>
                <div className="stat-card-label">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Topic progress */}
          {profile && profile.topics.length > 0 && (
            <>
              <div className="section-header">
                <h2 className="section-title">Topic Progress</h2>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 32 }}>
                {profile.topics.slice(0, 20).map(t => (
                  <span key={t.topic} style={{
                    padding: '6px 14px', borderRadius: 20, fontSize: '0.82rem', fontWeight: 600,
                    background: LEVEL_COLORS[t.status] + '22',
                    color: LEVEL_COLORS[t.status],
                    border: `1px solid ${LEVEL_COLORS[t.status]}44`,
                  }}>
                    {t.topic} — {t.status.replace('_', ' ')} ({Math.round(t.score * 100)}%)
                  </span>
                ))}
              </div>
            </>
          )}

          {/* Charts */}
          <div className="monitoring-grid">
            {topicData.length > 0 && (
              <div className="monitor-card">
                <p className="monitor-card-title">Topic Mastery</p>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={topicData} layout="vertical">
                    <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} fontSize={11} />
                    <YAxis type="category" dataKey="topic" width={100} fontSize={10} />
                    <Tooltip formatter={(v: number) => [`${v}%`, 'Mastery']} />
                    <Bar dataKey="mastery" fill="#a435f0" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {topicDistData.length > 0 && (
              <div className="monitor-card">
                <p className="monitor-card-title">Most Queried Topics</p>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={topicDistData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="topic" fontSize={10} />
                    <YAxis fontSize={11} />
                    <Tooltip />
                    <Line type="monotone" dataKey="queries" stroke="#a435f0" strokeWidth={2} dot={{ fill: '#a435f0', r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {topicData.length === 0 && topicDistData.length === 0 && (
            <div className="table-wrap" style={{ padding: 40, textAlign: 'center', marginBottom: 32 }}>
              <div style={{ fontSize: '3rem', marginBottom: 12 }}>📊</div>
              <p className="font-bold">No data yet</p>
              <p className="text-muted">Start chatting to track your learning progress!</p>
            </div>
          )}

          {/* Achievements */}
          <div className="section-header mt-6">
            <h2 className="section-title">Achievements</h2>
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {achievements.map(a => (
              <div key={a.label} style={{
                background: a.earned ? 'var(--brand-light)' : 'var(--bg)',
                border: `1px solid ${a.earned ? 'var(--brand)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-lg)', padding: '16px 20px', textAlign: 'center',
                opacity: a.earned ? 1 : 0.5, minWidth: 100,
              }}>
                <div style={{ fontSize: '2rem', marginBottom: 4 }}>{a.emoji}</div>
                <div style={{ fontSize: '0.78rem', fontWeight: 600, color: a.earned ? 'var(--brand)' : 'var(--muted)' }}>
                  {a.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
