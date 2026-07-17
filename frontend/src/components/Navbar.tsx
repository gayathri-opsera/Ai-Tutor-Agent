import { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useUser } from '../auth/UserContext';

const ROLE_COLOR: Record<string, string> = {
  Learner: '#a435f0', Creator: '#1e6055', Admin: '#c0392b', SuperAdmin: '#c0392b',
};

const LEARNER_LINKS = [
  { label: 'My Learning', path: '/learning' },
  { label: 'Browse',      path: '/content'  },
  { label: 'Progress',    path: '/progress' },
];

export function Navbar() {
  const location  = useLocation();
  const navigate  = useNavigate();
  const { user, logout } = useUser();
  const [query, setQuery]       = useState('');
  const [dropOpen, setDropOpen] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);

  const primaryRole = user?.isAdmin ? 'Admin'
    : user?.isCreator ? 'Creator'
    : 'Learner';
  const roleColor = ROLE_COLOR[primaryRole] ?? '#555';

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setDropOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) navigate(`/content?q=${encodeURIComponent(query)}`);
  };

  return (
    <nav className="navbar" role="navigation" aria-label="Main navigation">
      <Link to="/" className="navbar-logo">AI<span>Tutor</span></Link>

      <form className="navbar-search" onSubmit={handleSearch} role="search">
        <input value={query} onChange={e => setQuery(e.target.value)}
          placeholder="Search knowledge bases, topics…" aria-label="Search" />
        <button type="submit" aria-label="Search">🔍</button>
      </form>

      <div className="navbar-links">
        {LEARNER_LINKS.map(l => (
          <Link key={l.path} to={l.path}
            className={`navbar-link${location.pathname.startsWith(l.path) ? ' active' : ''}`}>
            {l.label}
          </Link>
        ))}
        <Link to="/chat"
          className={`navbar-link${location.pathname === '/chat' ? ' active' : ''}`}>
          💬 Chat
        </Link>

        {(user?.isCreator || user?.isAdmin) && (
          <>
            <Link to="/content/upload"
              className={`navbar-link${location.pathname === '/content/upload' ? ' active' : ''}`}>
              ⬆️ Upload
            </Link>
            <Link to="/content?create=1"
              className="navbar-link"
              style={{ color: '#f9a825' }}
            >
              ✚ Create Course
            </Link>
            <Link to="/creator/dashboard"
              className={`navbar-link${location.pathname === '/creator/dashboard' ? ' active' : ''}`}>
              📈 My Stats
            </Link>
          </>
        )}
        {user?.isAdmin && (
          <Link to="/admin/config"
            className={`navbar-link${location.pathname.startsWith('/admin') ? ' active' : ''}`}>
            ⚙️ Admin
          </Link>
        )}

        {/* ── User dropdown ─────────────────────────────────────────── */}
        <div ref={dropRef} style={{ position: 'relative', marginLeft: 8 }}>
          <button
            onClick={() => setDropOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '6px 12px', background: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.2)', borderRadius: 24,
              color: '#fff', cursor: 'pointer', fontSize: '0.85rem',
              transition: 'background 0.15s',
            }}
            aria-label="User menu" aria-expanded={dropOpen}
          >
            <span style={{ fontSize: '1.1rem' }}>{user?.avatar ?? '👤'}</span>
            <span style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.name?.split(' ')[0] ?? 'Guest'}
            </span>
            {user && (
              <span style={{
                background: roleColor, color: '#fff',
                fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: 8,
              }}>
                {primaryRole}
              </span>
            )}
            <span style={{ fontSize: '0.7rem', color: '#aaa' }}>▾</span>
          </button>

          {dropOpen && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 8px)', right: 0,
              background: '#fff', border: '1px solid var(--border)',
              borderRadius: 8, boxShadow: 'var(--shadow-lg)',
              minWidth: 240, zIndex: 200, overflow: 'hidden',
            }}>
              {user && (
                <div style={{ padding: '14px 16px', background: 'var(--bg)', borderBottom: '1px solid var(--border)' }}>
                  <p style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text)' }}>{user.name}</p>
                  <p style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>{user.email}</p>
                  <span style={{
                    display: 'inline-block', marginTop: 4,
                    background: `${roleColor}22`, color: roleColor,
                    fontSize: '0.72rem', fontWeight: 700, padding: '1px 8px', borderRadius: 8,
                  }}>
                    {primaryRole}
                  </span>
                </div>
              )}

              <div style={{ borderTop: '1px solid var(--border)', padding: '8px 0' }}>
                <Link to="/progress"
                  style={{ display: 'block', padding: '9px 16px', fontSize: '0.85rem', color: 'var(--text)' }}
                  onClick={() => setDropOpen(false)}>
                  📊 My Progress
                </Link>
                {user?.isAdmin && (
                  <Link to="/admin/monitoring"
                    style={{ display: 'block', padding: '9px 16px', fontSize: '0.85rem', color: 'var(--text)' }}
                    onClick={() => setDropOpen(false)}>
                    🖥️ Monitoring
                  </Link>
                )}
                {user?.isAdmin && (
                  <Link to="/admin/users"
                    style={{ display: 'block', padding: '9px 16px', fontSize: '0.85rem', color: 'var(--text)' }}
                    onClick={() => setDropOpen(false)}>
                    👥 User Approvals
                  </Link>
                )}
                <button
                  onClick={() => { logout(); setDropOpen(false); navigate('/'); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    width: '100%', padding: '9px 16px', background: 'transparent',
                    border: 'none', cursor: 'pointer', fontSize: '0.85rem',
                    color: 'var(--danger)', textAlign: 'left',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--danger-bg)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  🚪 Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
