import { useEffect, useState } from 'react';
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';

interface DashboardData {
  total_learners: number;
  total_courses: number;
  total_documents: number;
  total_chat_sessions: number;
  approval_status_distribution: Record<string, number>;
  top_courses_by_enrollment: { title: string; enrollments: number }[];
}

const STATUS_COLORS: Record<string, string> = {
  approved:                '#10b981',
  pending_review:          '#f59e0b',
  rejected:                '#ef4444',
  clarification_requested: '#3b82f6',
};

const STATUS_LABELS: Record<string, string> = {
  approved:                'Approved',
  pending_review:          'Pending Review',
  rejected:                'Rejected',
  clarification_requested: 'Needs Clarification',
};

export function AdminDashboardPage() {
  const [data, setData]       = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/analytics/admin/dashboard')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 4 }}>
        Platform Overview
      </h1>
      <p style={{ color: '#6b7280', marginBottom: '1.5rem' }}>
        Aggregate metrics across all services and users.
      </p>

      {error && (
        <div style={{ background: '#fee2e2', color: '#991b1b', padding: '0.75rem 1rem',
                      borderRadius: 6, marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {loading ? <p>Loading…</p> : data ? (
        <>
          {/* Summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                        gap: 16, marginBottom: '2rem' }}>
            <StatCard label="Total Learners"     value={data.total_learners}      color="#a435f0" />
            <StatCard label="Total Courses"      value={data.total_courses}       color="#1e6055" />
            <StatCard label="Documents Indexed"  value={data.total_documents}     color="#2563eb" />
            <StatCard label="Chat Sessions"      value={data.total_chat_sessions} color="#d97706" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            {/* Approval status pie chart */}
            <div style={{ background: '#fff', border: '1px solid #e5e7eb',
                          borderRadius: 8, padding: '1.25rem' }}>
              <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>
                Course Approval Status
              </h2>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={Object.entries(data.approval_status_distribution).map(
                      ([k, v]) => ({ name: STATUS_LABELS[k] ?? k, value: v, key: k })
                    )}
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    dataKey="value"
                  >
                    {Object.entries(data.approval_status_distribution).map(([k]) => (
                      <Cell key={k} fill={STATUS_COLORS[k] ?? '#94a3b8'} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Top courses bar chart */}
            <div style={{ background: '#fff', border: '1px solid #e5e7eb',
                          borderRadius: 8, padding: '1.25rem' }}>
              <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>
                Top Courses by Enrollment
              </h2>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={data.top_courses_by_enrollment.slice(0, 8).map(c => ({
                    name: c.title.length > 18 ? c.title.slice(0, 16) + '…' : c.title,
                    enrollments: c.enrollments,
                  }))}
                  margin={{ top: 4, right: 8, left: 0, bottom: 40 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-30} textAnchor="end" interval={0} tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="enrollments" fill="#a435f0" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
                  padding: '1.25rem', textAlign: 'center' }}>
      <p style={{ fontSize: '2rem', fontWeight: 700, color, marginBottom: 4 }}>{value}</p>
      <p style={{ fontSize: '0.85rem', color: '#6b7280' }}>{label}</p>
    </div>
  );
}
