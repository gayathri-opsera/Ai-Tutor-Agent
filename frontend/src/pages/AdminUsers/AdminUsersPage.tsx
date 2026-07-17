import { useEffect, useState } from 'react';

interface PendingUser {
  id: string;
  keycloak_id: string;
  email_hash: string;
  approval_status: string;
  created_at: string;
}

interface PendingListResponse {
  users: PendingUser[];
  total: number;
  limit: number;
  offset: number;
}

const ADMIN_USERS_API = '/api/v1/admin/users';
const AVAILABLE_ROLES = ['Learner', 'Creator', 'Admin'];

export function AdminUsersPage() {
  const [users, setUsers]         = useState<PendingUser[]>([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<Record<string, string[]>>({});

  const fetchPending = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${ADMIN_USERS_API}/pending`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: PendingListResponse = await res.json();
      setUsers(data.users);
      setTotal(data.total);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load pending users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPending(); }, []);

  const handleApprove = async (userId: string) => {
    const roles = selectedRoles[userId] ?? ['Learner'];
    try {
      const res = await fetch(`${ADMIN_USERS_API}/${userId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg(`User ${userId.slice(0, 8)}… approved with roles: ${roles.join(', ')}`);
      await fetchPending();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Approve failed');
    }
  };

  const handleReject = async (userId: string) => {
    if (!window.confirm('Reject this user? This action cannot be undone.')) return;
    try {
      const res = await fetch(`${ADMIN_USERS_API}/${userId}/reject`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg(`User ${userId.slice(0, 8)}… rejected`);
      await fetchPending();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Reject failed');
    }
  };

  const toggleRole = (userId: string, role: string) => {
    setSelectedRoles(prev => {
      const current = prev[userId] ?? ['Learner'];
      const next = current.includes(role)
        ? current.filter(r => r !== role)
        : [...current, role];
      return { ...prev, [userId]: next.length > 0 ? next : ['Learner'] };
    });
  };

  return (
    <div className="admin-users-page" style={{ padding: '1.5rem', maxWidth: 900, margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
        User Approval Dashboard
      </h1>
      <p style={{ color: '#666', marginBottom: '1.5rem' }}>
        {total} pending registration{total !== 1 ? 's' : ''} require review
      </p>

      {error && (
        <div style={{ background: '#fee2e2', color: '#991b1b', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem' }}>
          {error}
        </div>
      )}
      {actionMsg && (
        <div style={{ background: '#d1fae5', color: '#065f46', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem' }}>
          {actionMsg}
        </div>
      )}

      {loading ? (
        <p>Loading…</p>
      ) : users.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#6b7280', background: '#f9fafb', borderRadius: 8 }}>
          <p style={{ fontSize: '1.1rem' }}>No pending registrations</p>
          <p>All users have been reviewed.</p>
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ background: '#f3f4f6', borderBottom: '2px solid #e5e7eb' }}>
              <th style={{ padding: '0.75rem', textAlign: 'left' }}>Email Hash</th>
              <th style={{ padding: '0.75rem', textAlign: 'left' }}>Registered</th>
              <th style={{ padding: '0.75rem', textAlign: 'left' }}>Assign Roles</th>
              <th style={{ padding: '0.75rem', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                <td style={{ padding: '0.75rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                  {u.email_hash.slice(0, 16)}…
                </td>
                <td style={{ padding: '0.75rem', color: '#6b7280' }}>
                  {new Date(u.created_at).toLocaleDateString()}
                </td>
                <td style={{ padding: '0.75rem' }}>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {AVAILABLE_ROLES.map(role => {
                      const checked = (selectedRoles[u.id] ?? ['Learner']).includes(role);
                      return (
                        <label key={role} style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleRole(u.id, role)}
                          />
                          {role}
                        </label>
                      );
                    })}
                  </div>
                </td>
                <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                  <button
                    onClick={() => handleApprove(u.id)}
                    style={{
                      background: '#10b981', color: '#fff', border: 'none',
                      padding: '0.4rem 0.9rem', borderRadius: 4, cursor: 'pointer',
                      marginRight: 8, fontWeight: 600,
                    }}
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(u.id)}
                    style={{
                      background: '#ef4444', color: '#fff', border: 'none',
                      padding: '0.4rem 0.9rem', borderRadius: 4, cursor: 'pointer',
                      fontWeight: 600,
                    }}
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
