import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '0.6rem 0.85rem', fontSize: '0.95rem',
  border: '1px solid #d1d5db', borderRadius: 6, outline: 'none',
  boxSizing: 'border-box', transition: 'border-color 0.15s',
};

export function RegisterPage() {
  const navigate = useNavigate();
  const [email,    setEmail]    = useState('');
  const [name,     setName]     = useState('');
  const [password, setPassword] = useState('');
  const [confirm,  setConfirm]  = useState('');
  const [role,     setRole]     = useState<'Learner' | 'Creator'>('Learner');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [success,  setSuccess]  = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    if (password.length < 6)  { setError('Password must be at least 6 characters.'); return; }
    setLoading(true);
    try {
      const res = await fetch('/api/v1/auth/self-register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, full_name: name, password, desired_role: role }),
      });
      if (res.status === 409) { setError('This email is already registered.'); return; }
      if (!res.ok) {
        const data = await res.json().catch(() => ({})) as { detail?: string };
        setError(data.detail ?? 'Registration failed. Please try again.');
        return;
      }
      setSuccess(true);
    } catch {
      setError('Network error. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
                    justifyContent: 'center', background: '#f9fafb' }}>
        <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 4px 24px rgba(0,0,0,.1)',
                      padding: '2.5rem 2rem', width: '100%', maxWidth: 420, textAlign: 'center' }}>
          <div style={{ fontSize: '3rem', marginBottom: 16 }}>🎉</div>
          <h2 style={{ fontWeight: 700, fontSize: '1.3rem', marginBottom: 8 }}>Registration submitted!</h2>
          <p style={{ color: '#6b7280', fontSize: '0.9rem', marginBottom: 24 }}>
            Your account is pending admin approval. You'll be able to log in once an admin
            reviews and approves your request.
          </p>
          <Link to="/login"
            style={{ display: 'inline-block', padding: '0.6rem 1.5rem', background: '#a435f0',
                     color: '#fff', borderRadius: 6, fontWeight: 600, textDecoration: 'none',
                     fontSize: '0.9rem' }}>
            Back to Login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
                  justifyContent: 'center', background: '#f9fafb' }}>
      <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 4px 24px rgba(0,0,0,.1)',
                    padding: '2.5rem 2rem', width: '100%', maxWidth: 420 }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div style={{ fontSize: '2rem', fontWeight: 800, color: '#111827', marginBottom: 4 }}>
            🎓 AI <span style={{ color: '#a435f0' }}>Tutor</span>
          </div>
          <p style={{ color: '#6b7280', fontSize: '0.9rem' }}>Create your account</p>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Role selector */}
          <div style={{ display: 'flex', gap: 10, marginBottom: '1.25rem' }}>
            {(['Learner', 'Creator'] as const).map(r => (
              <button key={r} type="button"
                onClick={() => setRole(r)}
                style={{
                  flex: 1, padding: '0.6rem', border: '2px solid',
                  borderColor: role === r ? '#a435f0' : '#e5e7eb',
                  borderRadius: 8, background: role === r ? '#f5f3ff' : '#fff',
                  color: role === r ? '#7c3aed' : '#374151',
                  fontWeight: role === r ? 700 : 400, cursor: 'pointer',
                  fontSize: '0.9rem', transition: 'all 0.15s',
                }}>
                {r === 'Learner' ? '🎓 Learner' : '✏️ Creator'}
              </button>
            ))}
          </div>
          <p style={{ fontSize: '0.78rem', color: '#6b7280', marginBottom: '1rem', textAlign: 'center' }}>
            {role === 'Learner'
              ? 'Enrol in courses and track your learning progress.'
              : 'Build and publish courses for learners.'}
          </p>

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600,
                            color: '#374151', marginBottom: 6 }}>Full name</label>
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder="Your full name" required style={inputStyle}
              onFocus={e => (e.target.style.borderColor = '#a435f0')}
              onBlur={e  => (e.target.style.borderColor = '#d1d5db')} />
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600,
                            color: '#374151', marginBottom: 6 }}>Email address</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" required style={inputStyle}
              onFocus={e => (e.target.style.borderColor = '#a435f0')}
              onBlur={e  => (e.target.style.borderColor = '#d1d5db')} />
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600,
                            color: '#374151', marginBottom: 6 }}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Min. 6 characters" required style={inputStyle}
              onFocus={e => (e.target.style.borderColor = '#a435f0')}
              onBlur={e  => (e.target.style.borderColor = '#d1d5db')} />
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600,
                            color: '#374151', marginBottom: 6 }}>Confirm password</label>
            <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
              placeholder="••••••••" required style={inputStyle}
              onFocus={e => (e.target.style.borderColor = '#a435f0')}
              onBlur={e  => (e.target.style.borderColor = '#d1d5db')} />
          </div>

          {error && (
            <div style={{ background: '#fee2e2', color: '#991b1b', padding: '0.6rem 0.85rem',
                          borderRadius: 6, fontSize: '0.85rem', marginBottom: '1rem' }}>
              {error}
            </div>
          )}

          <button type="submit" disabled={loading}
            style={{ width: '100%', padding: '0.7rem', background: '#a435f0', color: '#fff',
                     border: 'none', borderRadius: 8, fontWeight: 700, fontSize: '1rem',
                     cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1 }}>
            {loading ? 'Submitting…' : `Register as ${role} →`}
          </button>
        </form>

        <p style={{ marginTop: '1.25rem', fontSize: '0.84rem', color: '#6b7280', textAlign: 'center' }}>
          Already have an account?{' '}
          <Link to="/login" style={{ color: '#a435f0', fontWeight: 600, textDecoration: 'none' }}>
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
