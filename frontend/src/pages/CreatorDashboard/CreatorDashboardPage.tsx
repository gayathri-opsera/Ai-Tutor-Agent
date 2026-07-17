import { useEffect, useState } from 'react';

interface CourseMetric {
  knowledge_base_id: string;
  title: string;
  age_group: string | null;
  approval_status: string;
  enrollment_count: number;
  avg_completion_pct: number;
  avg_assessment_score: number;
}

interface DashboardData {
  total_courses: number;
  total_enrollments: number;
  courses: CourseMetric[];
}

const STATUS_BADGE: Record<string, { bg: string; color: string; label: string }> = {
  approved:                { bg: '#d1fae5', color: '#065f46', label: 'Approved' },
  pending_review:          { bg: '#fef3c7', color: '#92400e', label: 'Pending' },
  rejected:                { bg: '#fee2e2', color: '#991b1b', label: 'Rejected' },
  clarification_requested: { bg: '#e0f2fe', color: '#0369a1', label: 'Needs Clarification' },
};

export function CreatorDashboardPage() {
  const [data, setData]       = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/analytics/creator/dashboard')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: '1.5rem', maxWidth: 960, margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 4 }}>
        My Course Dashboard
      </h1>
      <p style={{ color: '#6b7280', marginBottom: '1.5rem' }}>
        Metrics for courses you have published on the platform.
      </p>

      {error && (
        <div style={{ background: '#fee2e2', color: '#991b1b', padding: '0.75rem 1rem',
                      borderRadius: 6, marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {loading ? (
        <p>Loading…</p>
      ) : data ? (
        <>
          {/* Summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                        gap: 16, marginBottom: '2rem' }}>
            <StatCard label="Total Courses"     value={data.total_courses} />
            <StatCard label="Total Enrollments" value={data.total_enrollments} />
          </div>

          {/* Course table */}
          {data.courses.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', background: '#f9fafb',
                          borderRadius: 8, color: '#6b7280' }}>
              <p style={{ fontSize: '1.1rem' }}>No courses yet</p>
              <p>Upload content to create your first knowledge base.</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ background: '#f3f4f6', borderBottom: '2px solid #e5e7eb' }}>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Course</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Age Group</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Status</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right' }}>Enrollments</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right' }}>Avg Completion</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right' }}>Avg Score</th>
                </tr>
              </thead>
              <tbody>
                {data.courses.map(c => {
                  const badge = STATUS_BADGE[c.approval_status] ?? { bg: '#f3f4f6', color: '#374151', label: c.approval_status };
                  return (
                    <tr key={c.knowledge_base_id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                      <td style={{ padding: '0.75rem', fontWeight: 500 }}>{c.title}</td>
                      <td style={{ padding: '0.75rem', color: '#6b7280' }}>
                        {c.age_group ?? '—'}
                      </td>
                      <td style={{ padding: '0.75rem' }}>
                        <span style={{ background: badge.bg, color: badge.color,
                                       padding: '2px 10px', borderRadius: 12,
                                       fontSize: '0.78rem', fontWeight: 600 }}>
                          {badge.label}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                        {c.enrollment_count}
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                        {c.avg_completion_pct.toFixed(1)}%
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                        {c.avg_assessment_score > 0 ? c.avg_assessment_score.toFixed(1) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </>
      ) : null}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
                  padding: '1.25rem', textAlign: 'center' }}>
      <p style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--brand, #a435f0)',
                  marginBottom: 4 }}>{value}</p>
      <p style={{ fontSize: '0.85rem', color: '#6b7280' }}>{label}</p>
    </div>
  );
}
