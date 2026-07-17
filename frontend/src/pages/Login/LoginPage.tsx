import './LoginPage.css';

interface Props {
  onLogin: () => Promise<void>;
}

export function LoginPage({ onLogin }: Props) {
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          🎓 AI <span>Tutor</span>
        </div>
        <p className="login-tagline">
          Personalised learning powered by AI
        </p>

        <div className="login-features">
          <div className="login-feature">
            <span className="login-feature-icon">🤖</span>
            Chat with an AI tutor grounded in your course content
          </div>
          <div className="login-feature">
            <span className="login-feature-icon">📚</span>
            Browse courses and track your progress
          </div>
          <div className="login-feature">
            <span className="login-feature-icon">🎯</span>
            Take assessments and see skill mastery grow
          </div>
        </div>

        <button className="login-cta-btn" onClick={onLogin}>
          Continue with Keycloak →
        </button>

        <p className="login-footer">
          Secure sign-in via your organisation's identity provider
        </p>
      </div>
    </div>
  );
}
