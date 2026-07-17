import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  AreaChart, Area, CartesianGrid, Legend,
} from 'recharts';
import { useUser } from '../../auth/UserContext';

const LEARNER_API = '/api/v1/learner';

interface AssessmentScore {
  assessment_id: string;
  knowledge_base_id: string | null;
  score: number;
  assessment_type: string;
  submitted_at: string | null;
}
interface Streak {
  current_streak_days: number;
  longest_streak_days: number;
  last_active_date: string | null;
}
interface TopicEntry { topic: string; score: number; knowledge_base_id: string | null; }
interface DashboardData {
  user_id: string;
  overall_completion_percent: number;
  assessment_scores: AssessmentScore[];
  time_on_platform_minutes: number;
  streak: Streak;
  topic_progress: TopicEntry[];
}

function StatCard({ emoji, title, value, sub, accent }: {
  emoji: string; title: string; value: string | number; sub?: string; accent?: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-card-icon">{emoji}</div>
      <div className="stat-card-value" style={accent ? { color: accent } : undefined}>{value}</div>
      <div className="stat-card-label">{title}</div>
      {sub && <div className="text-sm text-muted" style={{ marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return `${h}h ${m}m`;
}

export function LearnerProgressDashboard() {
  const { user } = useUser();
  const [data, setData]       = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  const userId = user?.id ?? 'demo-user';

  useEffect(() => {
    fetch(`${LEARNER_API}/dashboard?user_id=${userId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: DashboardData) => { setData(d); setLoading(false); })
      .catch((e: Error) => { setError(e.message); setLoading(false); });
  }, [userId]);

  if (loading) return <div className="container" style={{ paddingTop: 60, textAlign: 'center' }}><div className="spinner" /></div>;
  if (error) return <div className="container" style={{ paddingTop: 40 }}><div className="error-banner">⚠️ {error}</div></div>;
  if (!data) return null;

  // Score trend over time
  const trendData = [...data.assessment_scores]
    .filter(s => s.submitted_at)
    .sort((a, b) => new Date(a.submitted_at!).getTime() - new Date(b.submitted_at!).getTime())
    .map(s => ({
      date: new Date(s.submitted_at!).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      score: Math.round(s.score),
      type: s.assessment_type,
    }));

  const topicData = data.topic_progress
    .filter(t => t.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 8)
    .map(t => ({
      topic: t.topic.length > 14 ? t.topic.slice(0, 12) + '…' : t.topic,
      score: Math.round(t.score * 100),
    }));

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <h1 className="dashboard-title">My Learning Dashboard</h1>
        <p className="dashboard-subtitle">Track your progress, time, and achievements.</p>
      </div>

      {/* Stat cards */}
      <div className="stats-row">
        <StatCard
          emoji="📊" title="Overall Completion" accent="#7c3aed"
          value={`${data.overall_completion_percent}%`}
          sub="across all enrolled courses"
        />
        <StatCard
          emoji="⏱️" title="Time on Platform" accent="#0ea5e9"
          value={formatTime(data.time_on_platform_minutes)}
          sub="total learning time"
        />
        <StatCard
          emoji="🔥" title="Current Streak" accent="#f59e0b"
          value={`${data.streak.current_streak_days}d`}
          sub={`Longest: ${data.streak.longest_streak_days}d`}
        />
        <StatCard
          emoji="🎯" title="Assessments Taken" accent="#10b981"
          value={data.assessment_scores.length}
          sub={data.streak.last_active_date ? `Last active: ${data.streak.last_active_date}` : undefined}
        />
      </div>

      {/* Progress bar */}
      <div className="chart-card">
        <div className="flex justify-between mb-2">
          <span className="font-semibold">Overall Completion</span>
          <span style={{ fontWeight: 700, color: '#7c3aed' }}>{data.overall_completion_percent}%</span>
        </div>
        <div className="progress-bar-container">
          <div className="progress-bar-fill" style={{ width: `${data.overall_completion_percent}%` }} />
        </div>
      </div>

      {/* Assessment score trend */}
      {trendData.length > 0 && (
        <div className="chart-card">
          <h2 className="chart-card-title">Assessment Score Trend</h2>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trendData}>
              <defs>
                <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#7c3aed" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#7c3aed" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => [`${v}%`, 'Score']} />
              <Area type="monotone" dataKey="score" stroke="#7c3aed" fill="url(#scoreGrad)" strokeWidth={2} dot={{ r: 4 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Topic proficiency BarChart */}
      {topicData.length > 0 && (
        <div className="chart-card">
          <h2 className="chart-card-title">Topic Proficiency</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={topicData} layout="vertical" margin={{ left: 0, right: 20 }}>
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
              <YAxis type="category" dataKey="topic" tick={{ fontSize: 11 }} width={100} />
              <Tooltip formatter={(v: number) => [`${v}%`, 'Score']} />
              <Bar dataKey="score" fill="#7c3aed" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
