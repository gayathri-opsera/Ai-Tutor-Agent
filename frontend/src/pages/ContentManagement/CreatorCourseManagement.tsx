import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KB_API } from '../../config/api';
import { useUser } from '../../auth/UserContext';

const AGE_GROUPS = [
  { value: '', label: '— Any age —' },
  { value: 'children', label: 'Children (up to 12)' },
  { value: 'teens', label: 'Teens (13–17)' },
  { value: 'adults', label: 'Adults (18+)' },
  { value: 'all_ages', label: 'All Ages' },
];

interface KB {
  id: string;
  name: string;
  description: string;
  age_group: string | null;
  approval_status: string;
  is_active: boolean;
  created_by_keycloak_id?: string | null;
}

const STATUS_BADGE: Record<string, { bg: string; color: string; label: string }> = {
  approved:                { bg: '#d1fae5', color: '#065f46', label: 'Approved' },
  pending_review:          { bg: '#fef3c7', color: '#92400e', label: 'Pending Review' },
  rejected:                { bg: '#fee2e2', color: '#991b1b', label: 'Rejected' },
  clarification_requested: { bg: '#e0f2fe', color: '#0369a1', label: 'Needs Clarification' },
};

interface FormState {
  name: string;
  description: string;
  age_group: string;
}

const EMPTY_FORM: FormState = { name: '', description: '', age_group: '' };

export function CreatorCourseManagement() {
  const { user } = useUser();
  const navigate  = useNavigate();

  const [courses, setCourses]         = useState<KB[]>([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [actionMsg, setActionMsg]     = useState<string | null>(null);
  const [showCreate, setShowCreate]   = useState(false);
  const [editingId, setEditingId]     = useState<string | null>(null);
  const [form, setForm]               = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting]   = useState(false);

  const myId = user?.keycloak_id ?? '';

  const fetchCourses = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${KB_API}?organization_id=default&include_archived=false`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setCourses(data.items ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load courses');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCourses(); }, []);

  const myCourses    = courses.filter(c => !c.created_by_keycloak_id || c.created_by_keycloak_id === myId);
  const otherCourses = courses.filter(c => c.created_by_keycloak_id && c.created_by_keycloak_id !== myId);

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    setSubmitting(true);
    try {
      const res = await fetch(KB_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          description: form.description,
          organization_id: 'default',
          age_group: form.age_group || null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg('Course created successfully');
      setShowCreate(false);
      setForm(EMPTY_FORM);
      await fetchCourses();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = async (kb: KB) => {
    if (!editingId) {
      setEditingId(kb.id);
      setForm({ name: kb.name, description: kb.description, age_group: kb.age_group ?? '' });
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`${KB_API}/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          description: form.description,
          age_group: form.age_group || null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg('Course updated');
      setEditingId(null);
      setForm(EMPTY_FORM);
      await fetchCourses();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Update failed');
    } finally {
      setSubmitting(false);
    }
  };

  const CourseRow = ({ kb, editable }: { kb: KB; editable: boolean }) => {
    const badge = STATUS_BADGE[kb.approval_status] ?? { bg: '#f3f4f6', color: '#374151', label: kb.approval_status };
    const isEditing = editingId === kb.id;
    return (
      <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
        <td style={{ padding: '0.75rem' }}>
          {isEditing ? (
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              style={{ width: '100%', padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4 }} />
          ) : (
            <span style={{ fontWeight: 500 }}>{kb.name}</span>
          )}
        </td>
        <td style={{ padding: '0.75rem', color: '#6b7280', maxWidth: 280 }}>
          {isEditing ? (
            <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              style={{ width: '100%', padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4 }} />
          ) : (
            <span style={{ fontSize: '0.85rem' }}>{kb.description || '—'}</span>
          )}
        </td>
        <td style={{ padding: '0.75rem' }}>
          {isEditing ? (
            <select value={form.age_group} onChange={e => setForm(f => ({ ...f, age_group: e.target.value }))}
              style={{ padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4 }}>
              {AGE_GROUPS.map(ag => <option key={ag.value} value={ag.value}>{ag.label}</option>)}
            </select>
          ) : (
            <span style={{ color: '#6b7280', fontSize: '0.85rem' }}>{kb.age_group ?? '—'}</span>
          )}
        </td>
        <td style={{ padding: '0.75rem' }}>
          <span style={{ background: badge.bg, color: badge.color, padding: '2px 10px',
                         borderRadius: 12, fontSize: '0.78rem', fontWeight: 600 }}>
            {badge.label}
          </span>
        </td>
        <td style={{ padding: '0.75rem', textAlign: 'right' }}>
          {editable && (
            isEditing ? (
              <>
                <button onClick={() => handleEdit(kb)} disabled={submitting}
                  style={{ background: '#10b981', color: '#fff', border: 'none',
                           padding: '4px 12px', borderRadius: 4, cursor: 'pointer',
                           marginRight: 6, fontWeight: 600, fontSize: '0.8rem' }}>
                  Save
                </button>
                <button onClick={() => { setEditingId(null); setForm(EMPTY_FORM); }}
                  style={{ background: '#6b7280', color: '#fff', border: 'none',
                           padding: '4px 12px', borderRadius: 4, cursor: 'pointer',
                           fontSize: '0.8rem' }}>
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button onClick={() => { setEditingId(null); setForm(EMPTY_FORM); handleEdit(kb); }}
                  style={{ background: 'none', border: '1px solid #d1d5db', padding: '4px 10px',
                           borderRadius: 4, cursor: 'pointer', fontSize: '0.8rem', marginRight: 6 }}>
                  ✏️ Edit
                </button>
                <button onClick={() => navigate(`/content/upload?kb=${kb.id}`)}
                  style={{ background: 'none', border: '1px solid #a435f0', color: '#a435f0',
                           padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontSize: '0.8rem' }}>
                  ⬆️ Upload
                </button>
              </>
            )
          )}
        </td>
      </tr>
    );
  };

  const CourseTable = ({ items, editable, emptyMsg }: { items: KB[]; editable: boolean; emptyMsg: string }) => (
    items.length === 0 ? (
      <p style={{ color: '#6b7280', padding: '1rem 0', fontSize: '0.9rem' }}>{emptyMsg}</p>
    ) : (
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
        <thead>
          <tr style={{ background: '#f3f4f6', borderBottom: '2px solid #e5e7eb' }}>
            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Name</th>
            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Description</th>
            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Age Group</th>
            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Status</th>
            <th style={{ padding: '0.75rem', textAlign: 'right' }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map(kb => <CourseRow key={kb.id} kb={kb} editable={editable} />)}
        </tbody>
      </table>
    )
  );

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 4 }}>My Courses</h1>
          <p style={{ color: '#6b7280' }}>Manage your knowledge base courses.</p>
        </div>
        <button
          onClick={() => { setShowCreate(true); setForm(EMPTY_FORM); }}
          style={{ background: '#a435f0', color: '#fff', border: 'none',
                   padding: '10px 20px', borderRadius: 6, cursor: 'pointer',
                   fontWeight: 700, fontSize: '0.9rem' }}>
          + New Course
        </button>
      </div>

      {error && (
        <div style={{ background: '#fee2e2', color: '#991b1b', padding: '0.75rem 1rem',
                      borderRadius: 6, marginBottom: '1rem' }}>
          {error} <button onClick={() => setError(null)} style={{ marginLeft: 8, background: 'none',
                   border: 'none', cursor: 'pointer', fontWeight: 700 }}>✕</button>
        </div>
      )}
      {actionMsg && (
        <div style={{ background: '#d1fae5', color: '#065f46', padding: '0.75rem 1rem',
                      borderRadius: 6, marginBottom: '1rem' }}>
          {actionMsg} <button onClick={() => setActionMsg(null)} style={{ marginLeft: 8,
                      background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}>✕</button>
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <div style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8,
                      padding: '1.25rem', marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>Create New Course</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>
                Name *
              </label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="Course name"
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                         borderRadius: 6, fontSize: '0.9rem', boxSizing: 'border-box' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>
                Age Group
              </label>
              <select value={form.age_group} onChange={e => setForm(f => ({ ...f, age_group: e.target.value }))}
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                         borderRadius: 6, fontSize: '0.9rem' }}>
                {AGE_GROUPS.map(ag => <option key={ag.value} value={ag.value}>{ag.label}</option>)}
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>
                Description
              </label>
              <textarea value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                rows={3} placeholder="Brief course description"
                style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                         borderRadius: 6, fontSize: '0.9rem', resize: 'vertical', boxSizing: 'border-box' }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: '1rem' }}>
            <button onClick={handleCreate} disabled={submitting || !form.name.trim()}
              style={{ background: '#a435f0', color: '#fff', border: 'none',
                       padding: '8px 20px', borderRadius: 6, cursor: 'pointer', fontWeight: 700 }}>
              {submitting ? 'Creating…' : 'Create Course'}
            </button>
            <button onClick={() => { setShowCreate(false); setForm(EMPTY_FORM); }}
              style={{ background: 'none', border: '1px solid #d1d5db',
                       padding: '8px 16px', borderRadius: 6, cursor: 'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? <p>Loading…</p> : (
        <>
          <section style={{ marginBottom: '2rem' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              My Courses ({myCourses.length})
            </h2>
            <CourseTable items={myCourses} editable={true}
              emptyMsg="You haven't created any courses yet. Click '+ New Course' to get started." />
          </section>

          {otherCourses.length > 0 && (
            <section>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
                Other Courses (read-only)
              </h2>
              <CourseTable items={otherCourses} editable={false}
                emptyMsg="No courses from other creators." />
            </section>
          )}
        </>
      )}
    </div>
  );
}
