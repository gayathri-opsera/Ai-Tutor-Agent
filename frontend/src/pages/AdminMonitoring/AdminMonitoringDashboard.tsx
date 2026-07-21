import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import { apiFetch } from '../../config/apiFetch';

const ANALYTICS_API = '/api/v1/analytics';

const SERVICES = [
  { name: 'LLM Gateway',        port: 18000 },
  { name: 'Embedding Service',  port: 8001  },
  { name: 'RAG Pipeline',       port: 8002  },
  { name: 'Chat Orchestrator',  port: 8004  },
  { name: 'Agent Reasoning',    port: 8005  },
  { name: 'Confidence Grader',  port: 8006  },
  { name: 'Learner Profile',    port: 8008  },
  { name: 'Assessment Engine',  port: 8010  },
  { name: 'Analytics',          port: 8011  },
];

const PIE_COLORS: Record<string, string> = {
  active: '#10b981', processing: '#f59e0b', retired: '#6b7280',
  error: '#ef4444', pending: '#a855f7',
};

interface AnalyticsSummary {
  session_count: number; query_volume: number; average_rating: number;
  topic_distribution: Record<string, number>;
  recent_events: { event_type: string; user_id: string; topic: string; created_at: string }[];
}
interface AdminDashboard {
  total_learners: number;
  total_courses: number;
  total_documents: number;
  total_chat_sessions: number;
  approval_status_distribution: Record<string, number>;
  top_courses_by_enrollment: { title: string; enrollments: number }[];
}

function StatCard({ emoji, title, value, sub, accent }: {
  emoji: string; title: string; value: string | number; sub?: string; accent?: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-card-icon">{emoji}</div>
      <div className="stat-card-value" style={{ color: accent }}>{value}</div>
      <div className="stat-card-label">{title}</div>
      {sub && <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export function AdminMonitoringDashboard() {
  const [summary, setSummary]       = useState<AnalyticsSummary | null>(null);
  const [adminData, setAdminData]   = useState<AdminDashboard | null>(null);
  const [loading, setLoading]       = useState(true);

  useEffect(() => {
    Promise.all([
      apiFetch(`${ANALYTICS_API}/summary`).then(r => r.ok ? r.json() : null),
      apiFetch(`${ANALYTICS_API}/admin/dashboard`).then(r => r.ok ? r.json() : null),
    ]).then(([s, a]) => {
      if (s) setSummary(s);
      if (a) setAdminData(a);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const topicData = summary
    ? Object.entries(summary.topic_distribution).slice(0, 8).map(([t, c]) => ({ topic: t.slice(0, 16), queries: c }))
    : [];

  const recentEvents = summary?.recent_events?.slice(0, 8) ?? [];

  const docStatusData = Object.entries(
    adminData?.approval_status_distribution ?? {}
  ).map(([status, count]) => ({ name: status, value: count }));

  const topCourses = adminData?.top_courses_by_enrollment ?? [];

  return (
    <div>
      <div className="page-header">
        <div className="container">
          <div className="page-header-row">
            <div>
              <h1>System Monitoring</h1>
              <p>Real-time metrics across all AI Tutor services</p>
            </div>
            <span className="badge badge-success">● All Systems Operational</span>
          </div>
        </div>
      </div>

      <div className="container">
        <div className="section">

          {/* Platform stat cards */}
          <div className="stats-row">
            <StatCard emoji="👥" title="Total Learners"
              value={loading ? '…' : String(adminData?.total_learners ?? summary?.session_count ?? 0)}
              accent="#7c3aed" />
            <StatCard emoji="📚" title="Total Courses"
              value={loading ? '…' : String(adminData?.total_courses ?? 0)}
              accent="#0ea5e9" />
            <StatCard emoji="📄" title="Total Documents"
              value={loading ? '…' : String(adminData?.total_documents ?? 0)}
              accent="#10b981" />
            <StatCard emoji="💬" title="Chat Sessions"
              value={loading ? '…' : String(adminData?.total_chat_sessions ?? 0)}
              sub="all time" accent="#f59e0b" />
          </div>

          {/* Charts row: document status pie + top topics bar */}
          <div className="monitoring-grid mb-6">
            {/* Document / approval status breakdown */}
            <div className="monitor-card">
              <p className="monitor-card-title">Course Approval Status</p>
              {docStatusData.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={docStatusData} cx="50%" cy="50%" outerRadius={80}
                      dataKey="value" label={({ name, percent }) => `${name} ${Math.round((percent ?? 0) * 100)}%`}
                      labelLine={false}>
                      {docStatusData.map((entry, i) => (
                        <Cell key={i} fill={PIE_COLORS[entry.name] ?? '#94a3b8'} />
                      ))}
                    </Pie>
                    <Legend formatter={(v) => v} />
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-muted" style={{ textAlign: 'center', paddingTop: 40 }}>
                  No course data yet
                </p>
              )}
            </div>

            {/* Top queried topics */}
            {topicData.length > 0 ? (
              <div className="monitor-card">
                <p className="monitor-card-title">Top Queried Topics</p>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={topicData} layout="vertical">
                    <XAxis type="number" fontSize={11} />
                    <YAxis type="category" dataKey="topic" width={110} fontSize={10} />
                    <Tooltip />
                    <Bar dataKey="queries" fill="#a435f0" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="monitor-card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 220 }}>
                <p className="text-muted">No analytics data yet</p>
              </div>
            )}
          </div>

          {/* Top courses by enrollment */}
          {topCourses.length > 0 && (
            <div className="monitor-card" style={{ marginBottom: '1.5rem' }}>
              <p className="monitor-card-title">Top 10 Courses by Enrollment</p>
              <table style={{ width: '100%', fontSize: '0.82rem', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f9fafb' }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px', fontSize: '0.72rem', color: '#6b7280', fontWeight: 600 }}>Course</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px', fontSize: '0.72rem', color: '#6b7280', fontWeight: 600 }}>Enrolled</th>
                  </tr>
                </thead>
                <tbody>
                  {topCourses.slice(0, 10).map((c, i) => (
                    <tr key={i} style={{ borderTop: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '6px 8px', fontWeight: 500 }}>{c.title}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', color: '#7c3aed', fontWeight: 600 }}>{c.enrollments}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Recent events */}
          {recentEvents.length > 0 && (
            <div className="monitor-card" style={{ marginBottom: '1.5rem' }}>
              <p className="monitor-card-title">Recent Events</p>
              <table style={{ width: '100%', fontSize: '0.78rem' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', color: 'var(--muted)', fontSize: '0.68rem', fontWeight: 600, paddingBottom: 6 }}>Type</th>
                    <th style={{ textAlign: 'left', color: 'var(--muted)', fontSize: '0.68rem', fontWeight: 600, paddingBottom: 6 }}>User</th>
                    <th style={{ textAlign: 'left', color: 'var(--muted)', fontSize: '0.68rem', fontWeight: 600, paddingBottom: 6 }}>Topic</th>
                  </tr>
                </thead>
                <tbody>
                  {recentEvents.map((e, i) => (
                    <tr key={i}>
                      <td style={{ padding: '5px 0' }}>
                        <span style={{
                          background: e.event_type === 'session.created' ? '#ede9fe' : '#dcfce7',
                          color: e.event_type === 'session.created' ? '#7c3aed' : '#166534',
                          borderRadius: 6, padding: '2px 7px', fontSize: '0.68rem', fontWeight: 600,
                        }}>
                          {e.event_type}
                        </span>
                      </td>
                      <td style={{ padding: '5px 8px', color: 'var(--muted)' }}>{e.user_id?.slice(0, 12) || '—'}</td>
                      <td style={{ padding: '5px 0', color: 'var(--text)', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {e.topic?.slice(0, 40) || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Service Health */}
          <div className="monitor-card">
            <p className="monitor-card-title">Service Registry</p>
            <table style={{ width: '100%', fontSize: '0.82rem' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.72rem', padding: '4px 0' }}>Service</th>
                  <th style={{ textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.72rem', padding: '4px 0' }}>Port</th>
                  <th style={{ textAlign: 'right', color: 'var(--muted)', fontWeight: 600, fontSize: '0.72rem', padding: '4px 0' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {SERVICES.map(s => (
                  <tr key={s.name}>
                    <td style={{ padding: '6px 0' }}>{s.name}</td>
                    <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>{s.port}</td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="badge badge-success" style={{ fontSize: '0.68rem' }}>● running</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
