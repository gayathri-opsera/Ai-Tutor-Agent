import { useState } from 'react';
import './LoginPage.css';

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
}

export function LoginPage({ onLogin }: Props) {
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) { setError('Please enter email and password.'); return; }
    setError('');
    setLoading(true);
    try {
      await onLogin(email.trim(), password);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          🎓 AI <span>Tutor</span>
        </div>
        <p className="login-tagline">
          Personalised learning powered by AI
        </p>

        <form onSubmit={handleSubmit} style={{ width: '100%', marginTop: '1.5rem' }}>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600,
                            color: '#374151', marginBottom: 6 }}>
              Email address
            </label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@ai-tutor.local"
              autoComplete="email"
              required
              style={{
                width: '100%', padding: '0.6rem 0.85rem', fontSize: '0.95rem',
                border: '1px solid #d1d5db', borderRadius: 6, outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => (e.target.style.borderColor = '#a435f0')}
              onBlur={e  => (e.target.style.borderColor = '#d1d5db')}
            />
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600,
                            color: '#374151', marginBottom: 6 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              style={{
                width: '100%', padding: '0.6rem 0.85rem', fontSize: '0.95rem',
                border: '1px solid #d1d5db', borderRadius: 6, outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => (e.target.style.borderColor = '#a435f0')}
              onBlur={e  => (e.target.style.borderColor = '#d1d5db')}
            />
          </div>

          {error && (
            <div style={{ background: '#fee2e2', color: '#991b1b', padding: '0.6rem 0.85rem',
                          borderRadius: 6, fontSize: '0.85rem', marginBottom: '1rem' }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="login-cta-btn"
            disabled={loading}
            style={{ width: '100%', marginTop: 0 }}
          >
            {loading ? 'Signing in…' : 'Sign In →'}
          </button>
        </form>

        <p style={{ marginTop: '1.25rem', fontSize: '0.84rem', color: '#6b7280', textAlign: 'center' }}>
          New here?{' '}
          <a href="/register" style={{ color: '#a435f0', fontWeight: 600, textDecoration: 'none' }}>
            Create an account
          </a>
        </p>

        <p className="login-footer">
          Secure sign-in via your organisation's identity provider
        </p>
      </div>
    </div>
  );
}
