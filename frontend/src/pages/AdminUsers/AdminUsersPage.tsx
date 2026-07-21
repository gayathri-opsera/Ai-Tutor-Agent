import { useEffect, useState } from 'react';
import { apiFetch } from '../../config/apiFetch';

interface User {
  id: string;
  keycloak_id: string;
  email_hash: string;
  email: string;
  full_name: string;
  approval_status: string;
  roles: string[];
  created_at: string;
}

interface UsersResponse {
  users: User[];
  total: number;
}

const ADMIN_USERS_API = '/api/v1/admin/users';
const AVAILABLE_ROLES = ['Learner', 'Creator', 'Admin'];
const STATUS_OPTIONS   = ['approved', 'pending', 'rejected'];

const STATUS_BADGE: Record<string, { bg: string; color: string }> = {
  approved: { bg: '#d1fae5', color: '#065f46' },
  pending:  { bg: '#fef9c3', color: '#92400e' },
  rejected: { bg: '#fee2e2', color: '#991b1b' },
};

const ROLE_COLORS: Record<string, { bg: string; color: string }> = {
  Admin:   { bg: '#fce7f3', color: '#9d174d' },
  Creator: { bg: '#e0e7ff', color: '#3730a3' },
  Learner: { bg: '#dcfce7', color: '#166534' },
};

export function AdminUsersPage() {
  const [users, setUsers]                 = useState<User[]>([]);
  const [total, setTotal]                 = useState(0);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState<string | null>(null);
  const [actionMsg, setActionMsg]         = useState<string | null>(null);
  const [statusFilter, setStatusFilter]   = useState<string>('all');
  const [editingId, setEditingId]         = useState<string | null>(null);
  const [editRoles, setEditRoles]         = useState<string[]>([]);
  const [editStatus, setEditStatus]       = useState<string>('');
  const [saving, setSaving]               = useState(false);
  const [approvingId, setApprovingId]     = useState<string | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const url = statusFilter === 'all'
        ? `${ADMIN_USERS_API}?limit=100`
        : `${ADMIN_USERS_API}?limit=100&status=${statusFilter}`;
      const res = await apiFetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: UsersResponse = await res.json();
      setUsers(data.users);
      setTotal(data.total);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, [statusFilter]);

  const flash = (msg: string) => {
    setActionMsg(msg);
    setTimeout(() => setActionMsg(null), 3500);
  };

  const startEdit = (u: User) => {
    setEditingId(u.id);
    setEditRoles([...u.roles]);
    setEditStatus(u.approval_status);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditRoles([]);
    setEditStatus('');
  };

  const saveEdit = async (userId: string) => {
    setSaving(true);
    try {
      const res = await apiFetch(`${ADMIN_USERS_API}/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_status: editStatus, roles: editRoles }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      flash('User updated successfully');
      cancelEdit();
      await fetchUsers();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Update failed');
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async (u: User) => {
    setApprovingId(u.id);
    try {
      const roles = u.roles.length > 0 ? u.roles : ['Learner'];
      const res = await apiFetch(`${ADMIN_USERS_API}/${u.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      flash(`✅ ${u.email || u.email_hash.slice(0, 12)} approved`);
      await fetchUsers();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Approval failed');
    } finally {
      setApprovingId(null);
    }
  };

  const handleDelete = async (u: User) => {
    const label = u.email || u.email_hash.slice(0, 14) + '…';
    if (!window.confirm(`Delete ${label}?\n\nThis removes their account and all associated data.`)) return;
    try {
      const res = await apiFetch(`${ADMIN_USERS_API}/${u.id}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
      flash('User deleted');
      await fetchUsers();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    }
  };

  const toggleEditRole = (role: string) => {
    setEditRoles(prev =>
      prev.includes(role) ? prev.filter(r => r !== role) : [...prev, role]
    );
  };

  const pendingCount = users.filter(u => u.approval_status === 'pending').length;

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 4 }}>User Management</h1>
          <p style={{ color: '#6b7280', fontSize: '0.9rem' }}>
            {total} user{total !== 1 ? 's' : ''}
            {pendingCount > 0 && (
              <span style={{ marginLeft: 8, background: '#fef9c3', color: '#92400e',
                             padding: '2px 8px', borderRadius: 10, fontSize: '0.78rem', fontWeight: 700 }}>
                {pendingCount} pending approval
              </span>
            )}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {(['all', ...STATUS_OPTIONS] as const).map(s => (
            <button key={s} onClick={() => setStatusFilter(s)} style={{
              padding: '0.35rem 0.9rem', borderRadius: 20, fontSize: '0.8rem',
              fontWeight: 600, cursor: 'pointer', border: '1.5px solid',
              background: statusFilter === s ? 'var(--primary)' : 'transparent',
              color: statusFilter === s ? '#fff' : 'var(--primary)',
              borderColor: 'var(--primary)', textTransform: 'capitalize',
            }}>
              {s}
            </button>
          ))}
        </div>
      </div>

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
        <p style={{ color: '#6b7280' }}>Loading…</p>
      ) : users.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#6b7280', background: '#f9fafb', borderRadius: 8 }}>
          <p style={{ fontSize: '1.1rem' }}>No users found</p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
            <thead>
              <tr style={{ background: '#f3f4f6', borderBottom: '2px solid #e5e7eb' }}>
                <th style={{ padding: '0.75rem', textAlign: 'left' }}>User</th>
                <th style={{ padding: '0.75rem', textAlign: 'left' }}>Status</th>
                <th style={{ padding: '0.75rem', textAlign: 'left' }}>Roles</th>
                <th style={{ padding: '0.75rem', textAlign: 'left' }}>Registered</th>
                <th style={{ padding: '0.75rem', textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => {
                const isEditing = editingId === u.id;
                const badge     = STATUS_BADGE[u.approval_status] ?? STATUS_BADGE['pending'];
                const isPending = u.approval_status === 'pending';
                return (
                  <tr key={u.id} style={{
                    borderBottom: '1px solid #e5e7eb',
                    background: isEditing ? '#f0fdf4' : isPending ? '#fffbeb' : 'transparent',
                  }}>
                    {/* ── User column ── */}
                    <td style={{ padding: '0.75rem', minWidth: 200 }}>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#111827' }}>
                        {u.full_name || '—'}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: '#6b7280', marginTop: 2 }}>
                        {u.email || u.email_hash.slice(0, 20) + '…'}
                      </div>
                    </td>

                    {/* ── Status column ── */}
                    <td style={{ padding: '0.75rem' }}>
                      {isEditing ? (
                        <select value={editStatus} onChange={e => setEditStatus(e.target.value)}
                          style={{ padding: '0.25rem 0.5rem', borderRadius: 4, border: '1px solid #d1d5db', fontSize: '0.85rem' }}>
                          {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                      ) : (
                        <span style={{ padding: '2px 10px', borderRadius: 10, fontSize: '0.78rem', fontWeight: 700, ...badge }}>
                          {u.approval_status}
                        </span>
                      )}
                    </td>

                    {/* ── Roles column ── */}
                    <td style={{ padding: '0.75rem' }}>
                      {isEditing ? (
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          {AVAILABLE_ROLES.map(role => (
                            <label key={role} style={{ display: 'flex', alignItems: 'center', gap: 3, cursor: 'pointer', fontSize: '0.82rem' }}>
                              <input type="checkbox" checked={editRoles.includes(role)}
                                onChange={() => toggleEditRole(role)} />
                              {role}
                            </label>
                          ))}
                        </div>
                      ) : (
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {u.roles.length > 0
                            ? u.roles.map(r => {
                                const c = ROLE_COLORS[r] ?? { bg: '#f3f4f6', color: '#374151' };
                                return (
                                  <span key={r} style={{ ...c, padding: '1px 8px', borderRadius: 8, fontSize: '0.75rem', fontWeight: 600 }}>
                                    {r}
                                  </span>
                                );
                              })
                            : <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>—</span>
                          }
                        </div>
                      )}
                    </td>

                    {/* ── Registered column ── */}
                    <td style={{ padding: '0.75rem', color: '#6b7280', fontSize: '0.8rem' }}>
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>

                    {/* ── Actions column ── */}
                    <td style={{ padding: '0.75rem', textAlign: 'center', whiteSpace: 'nowrap' }}>
                      {isEditing ? (
                        <>
                          <button onClick={() => saveEdit(u.id)} disabled={saving}
                            style={{ background: '#10b981', color: '#fff', border: 'none',
                                     padding: '0.35rem 0.8rem', borderRadius: 4, cursor: 'pointer',
                                     fontWeight: 600, marginRight: 6, fontSize: '0.82rem' }}>
                            {saving ? '…' : 'Save'}
                          </button>
                          <button onClick={cancelEdit}
                            style={{ background: '#f3f4f6', color: '#374151', border: '1px solid #d1d5db',
                                     padding: '0.35rem 0.8rem', borderRadius: 4, cursor: 'pointer', fontSize: '0.82rem' }}>
                            Cancel
                          </button>
                        </>
                      ) : (
                        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
                          {isPending && (
                            <button onClick={() => handleApprove(u)}
                              disabled={approvingId === u.id}
                              style={{ background: '#10b981', color: '#fff', border: 'none',
                                       padding: '0.35rem 0.8rem', borderRadius: 4, cursor: 'pointer',
                                       fontWeight: 700, fontSize: '0.82rem' }}>
                              {approvingId === u.id ? '…' : '✓ Approve'}
                            </button>
                          )}
                          <button onClick={() => startEdit(u)}
                            style={{ background: '#3b82f6', color: '#fff', border: 'none',
                                     padding: '0.35rem 0.8rem', borderRadius: 4, cursor: 'pointer',
                                     fontWeight: 600, fontSize: '0.82rem' }}>
                            Edit
                          </button>
                          <button onClick={() => handleDelete(u)}
                            style={{ background: '#ef4444', color: '#fff', border: 'none',
                                     padding: '0.35rem 0.8rem', borderRadius: 4, cursor: 'pointer',
                                     fontWeight: 600, fontSize: '0.82rem' }}>
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
