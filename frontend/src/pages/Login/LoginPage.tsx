interface Props {
  onLogin: () => Promise<void>;
}

export function LoginPage({ onLogin }: Props) {
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
          RAG · Vector Search · AI-Powered Learning
        </p>
      </div>

      {/* Card */}
      <div style={{
        background: '#fff', borderRadius: 12, padding: '40px 48px',
        width: '100%', maxWidth: 440, boxShadow: '0 24px 64px rgba(0,0,0,0.4)',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: '2.5rem', marginBottom: 16 }}>🔐</div>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 8 }}>
          Sign in to AI Tutor
        </h2>
        <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginBottom: 32, lineHeight: 1.6 }}>
          Authenticate securely with your organisation's identity provider.
        </p>

        <button
          onClick={onLogin}
          style={{
            width: '100%', padding: '14px 24px',
            background: 'var(--brand, #a435f0)', color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer',
            fontWeight: 700, fontSize: '1rem',
            transition: 'opacity 0.15s',
          }}
          onMouseEnter={e => ((e.target as HTMLButtonElement).style.opacity = '0.88')}
          onMouseLeave={e => ((e.target as HTMLButtonElement).style.opacity = '1')}
        >
          Continue with Keycloak →
        </button>

        <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 24 }}>
          🔒 OAuth 2.0 PKCE · Secured via Keycloak
        </p>
      </div>

      <div style={{ marginTop: 32, textAlign: 'center' }}>
        <p style={{ color: '#666', fontSize: '0.78rem' }}>
          AI Tutor Platform · All services running
        </p>
      </div>
    </div>
  );
}
