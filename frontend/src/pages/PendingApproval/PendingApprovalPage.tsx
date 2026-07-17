import { useUser } from '../../auth/UserContext';

export function PendingApprovalPage() {
  const { logout } = useUser();

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--header-bg)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      <div style={{
        background: '#fff', borderRadius: 12, padding: '48px 56px',
        maxWidth: 520, width: '100%', textAlign: 'center',
        boxShadow: '0 24px 64px rgba(0,0,0,0.4)',
      }}>
        <div style={{ fontSize: '3rem', marginBottom: 16 }}>⏳</div>
        <h1 style={{ fontSize: '1.6rem', fontWeight: 800, marginBottom: 8 }}>
          Registration Pending Review
        </h1>
        <p style={{ color: 'var(--muted)', lineHeight: 1.7, marginBottom: 32 }}>
          Your account has been created and is awaiting approval by an
          administrator. You will be able to access the platform once your
          registration has been reviewed.
        </p>
        <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: 32 }}>
          This usually takes 1–2 business days. If you have questions,
          contact <a href="mailto:support@ai-tutor.local" style={{ color: 'var(--brand)' }}>
            support@ai-tutor.local
          </a>.
        </p>
        <button
          onClick={() => logout()}
          style={{
            padding: '10px 24px', background: 'var(--header-bg)',
            color: '#fff', border: 'none', borderRadius: 6,
            cursor: 'pointer', fontWeight: 600, fontSize: '0.9rem',
          }}
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}
