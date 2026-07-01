import { DEMO_USERS, useUser } from '../../auth/UserContext';

const ROLE_COLORS: Record<string, string> = {
  Learner: '#a435f0',
  Creator: '#1e6055',
  Admin:   '#c0392b',
};

const ROLE_DESC: Record<string, string> = {
  Learner: 'Browse knowledge bases, chat with AI, track your progress.',
  Creator: 'Upload documents, manage knowledge bases, ingest content.',
  Admin:   'Configure the platform, view monitoring, manage all users.',
};

export function LoginPage() {
  const { login } = useUser();

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--header-bg)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      {/* Logo */}
      <div style={{ marginBottom: 40, textAlign: 'center' }}>
        <h1 style={{ color: '#fff', fontSize: '2.5rem', fontWeight: 800, letterSpacing: '-1px' }}>
          AI<span style={{ color: 'var(--brand)' }}>Tutor</span>
        </h1>
        <p style={{ color: '#aaa', marginTop: 8, fontSize: '1rem' }}>
          RAG · Vector Search · AI-Powered
        </p>
      </div>

      {/* Card */}
      <div style={{
        background: '#fff', borderRadius: 12, padding: '40px 48px',
        width: '100%', maxWidth: 480, boxShadow: '0 24px 64px rgba(0,0,0,0.4)',
      }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 6 }}>
          Sign in to AI Tutor
        </h2>
        <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginBottom: 28 }}>
          Select a demo account to continue. No password required.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {DEMO_USERS.map(u => (
            <button
              key={u.id}
              onClick={() => login(u)}
              style={{
                display: 'flex', alignItems: 'center', gap: 16,
                padding: '16px 20px', background: '#f7f9fa',
                border: '1px solid var(--border)', borderRadius: 8,
                cursor: 'pointer', transition: 'all 0.15s', textAlign: 'left',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = ROLE_COLORS[u.role];
                (e.currentTarget as HTMLButtonElement).style.background = '#fff';
                (e.currentTarget as HTMLButtonElement).style.boxShadow = `0 0 0 3px ${ROLE_COLORS[u.role]}22`;
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)';
                (e.currentTarget as HTMLButtonElement).style.background = '#f7f9fa';
                (e.currentTarget as HTMLButtonElement).style.boxShadow = 'none';
              }}
            >
              {/* Avatar */}
              <div style={{
                width: 48, height: 48, borderRadius: '50%',
                background: `${ROLE_COLORS[u.role]}22`,
                border: `2px solid ${ROLE_COLORS[u.role]}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '1.4rem', flexShrink: 0,
              }}>
                {u.avatar}
              </div>

              {/* Info */}
              <div style={{ flex: 1 }}>
                <p style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: 2 }}>{u.name}</p>
                <p style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>{u.email}</p>
                <p style={{ fontSize: '0.75rem', color: ROLE_COLORS[u.role], fontWeight: 600, marginTop: 2 }}>
                  {u.role} · {ROLE_DESC[u.role]}
                </p>
              </div>

              {/* Arrow */}
              <span style={{ color: 'var(--muted)', fontSize: '1.1rem' }}>→</span>
            </button>
          ))}
        </div>

        <p style={{ fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'center', marginTop: 24 }}>
          🔒 Demo environment · Auth via Keycloak in production
        </p>
      </div>

      {/* Footer */}
      <div style={{ marginTop: 32, textAlign: 'center' }}>
        <p style={{ color: '#666', fontSize: '0.78rem' }}>
          AI Tutor Platform · All 19 services running locally
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 8 }}>
          {['LLM Gateway ✅', 'RAG Pipeline ✅', 'Chat ✅', 'AI Ready ✅'].map(s => (
            <span key={s} style={{ fontSize: '0.72rem', color: '#555', background: '#222', padding: '3px 8px', borderRadius: 4 }}>{s}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
