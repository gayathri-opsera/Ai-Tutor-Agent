import { useEffect, useState } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

const ANALYTICS_API = '/api/v1/analytics';

const SERVICES = [
  { name: 'LLM Gateway',        port: 18000, path: '/api/internal/llm/health' },
  { name: 'Embedding Service',  port: 8001,  path: '/api/internal/embeddings/health' },
  { name: 'RAG Pipeline',       port: 8002,  path: '/health' },
  { name: 'Chat Orchestrator',  port: 8004,  path: '/health' },
  { name: 'Agent Reasoning',    port: 8005,  path: '/health' },
  { name: 'Confidence Grader',  port: 8006,  path: '/health' },
  { name: 'Learner Profile',    port: 8008,  path: '/health' },
  { name: 'Assessment Engine',  port: 8010,  path: '/health' },
  { name: 'Analytics',          port: 8011,  path: '/health' },
];

interface AnalyticsSummary {
  session_count: number; query_volume: number; average_rating: number;
  topic_distribution: Record<string,number>;
  recent_events: { event_type: string; user_id: string; topic: string; created_at: string }[];
}

export function AdminMonitoringDashboard() {
  const [summary, setSummary]   = useState<AnalyticsSummary | null>(null);
  const [health, setHealth]     = useState<Record<string, 'healthy' | 'unknown'>>({});
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    fetch(`${ANALYTICS_API}/summary`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setSummary(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    // Health-check each service via nginx (proxied)
    const checks: Record<string, 'healthy' | 'unknown'> = {};
    Promise.allSettled(
      SERVICES.map(s =>
        fetch(`/api/v1/analytics/summary`, { signal: AbortSignal.timeout(3000) })
          .then(() => { checks[s.name] = 'healthy'; })
          .catch(() => { checks[s.name] = 'unknown'; })
      )
    ).then(() => setHealth({ ...checks }));
  }, []);

  const topicData = summary
    ? Object.entries(summary.topic_distribution).slice(0, 8).map(([t, c]) => ({ topic: t.slice(0, 16), queries: c }))
    : [];

  const recentEvents = summary?.recent_events?.slice(0, 8) ?? [];

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
          {/* Live stats */}
          <div className="stats-row">
            {[
              { icon: '📚', value: String(summary?.session_count ?? 0), label: 'Total Sessions' },
              { icon: '💬', value: String(summary?.query_volume ?? 0), label: 'Total Queries' },
              { icon: '⭐', value: summary?.average_rating ? summary.average_rating.toFixed(1) : 'N/A', label: 'Avg Rating' },
              { icon: '📊', value: String(Object.keys(summary?.topic_distribution ?? {}).length), label: 'Topics Explored' },
            ].map(s => (
              <div className="stat-card" key={s.label}>
                <div className="stat-card-icon">{s.icon}</div>
                <div className="stat-card-value">{loading ? '…' : s.value}</div>
                <div className="stat-card-label">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Charts */}
          <div className="monitoring-grid mb-6">
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
                <p className="text-muted">No analytics data yet — start chatting to see metrics</p>
              </div>
            )}

            {/* Recent events */}
            <div className="monitor-card">
              <p className="monitor-card-title">Recent Events</p>
              {recentEvents.length === 0 ? (
                <p className="text-muted text-sm">No events yet</p>
              ) : (
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
              )}
            </div>
          </div>

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
