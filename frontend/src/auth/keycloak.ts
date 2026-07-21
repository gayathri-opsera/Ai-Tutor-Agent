/**
 * Keycloak PKCE authentication service.
 *
 * Reads config from environment variables injected at build time:
 *   VITE_KEYCLOAK_URL     — base URL of the Keycloak instance
 *   VITE_KEYCLOAK_REALM   — realm name (default: ai-tutor)
 *   VITE_KEYCLOAK_CLIENT  — public OIDC client id (default: ai-tutor-api)
 *
 * Falls back to a dev-only mock when VITE_AUTH_MOCK=true is set,
 * preserving the previous demo-user behaviour for local development.
 */

import Keycloak from 'keycloak-js';

// ── Config ────────────────────────────────────────────────────────────────────

const KEYCLOAK_URL    = import.meta.env.VITE_KEYCLOAK_URL    ?? 'http://localhost:8080';
const KEYCLOAK_REALM  = import.meta.env.VITE_KEYCLOAK_REALM  ?? 'ai-tutor';
const KEYCLOAK_CLIENT = import.meta.env.VITE_KEYCLOAK_CLIENT ?? 'ai-tutor-api';
const AUTH_MOCK       = import.meta.env.VITE_AUTH_MOCK === 'true';

// Token refresh proactively when less than 30 seconds remain.
const TOKEN_MIN_VALIDITY_SECONDS = 30;

// ── Keycloak singleton ────────────────────────────────────────────────────────

let kc: Keycloak | null = null;

function getInstance(): Keycloak {
  if (!kc) {
    kc = new Keycloak({
      url:      KEYCLOAK_URL,
      realm:    KEYCLOAK_REALM,
      clientId: KEYCLOAK_CLIENT,
    });
  }
  return kc;
}

// ── Parsed token claims ───────────────────────────────────────────────────────

export interface AuthUser {
  id:        string;       // Keycloak subject UUID
  name:      string;
  email:     string;
  roles:     string[];     // realm roles from token
  token:     string;       // current access token (JWT)
  idToken:   string;
}

function parseClaims(kc: Keycloak): AuthUser | null {
  if (!kc.authenticated || !kc.tokenParsed) return null;
  const p = kc.tokenParsed as Record<string, unknown>;
  const realmRoles = (p['realm_access'] as { roles?: string[] })?.roles ?? [];
  // Map Keycloak realm roles to our application roles (case-insensitive).
  const appRoles = realmRoles.filter(r =>
    ['Admin', 'SuperAdmin', 'Creator', 'Learner'].some(ar => ar.toLowerCase() === r.toLowerCase()),
  ).map(r => r.charAt(0).toUpperCase() + r.slice(1).toLowerCase());

  return {
    id:      (p['sub'] as string) ?? '',
    name:    (p['name'] as string) ?? (p['preferred_username'] as string) ?? 'User',
    email:   (p['email'] as string) ?? '',
    roles:   appRoles.length > 0 ? appRoles : ['Learner'],
    token:   kc.token ?? '',
    idToken: kc.idToken ?? '',
  };
}

// ── Mock user roster for local dev ────────────────────────────────────────────

const MOCK_CREDENTIALS: Record<string, { password: string; user: AuthUser }> = {
  'admin@ai-tutor.local': {
    password: 'Admin@123',
    user: {
      id:      'aaaaaaaa-0001-0000-0000-000000000001',
      name:    'Alice Admin',
      email:   'admin@ai-tutor.local',
      roles:   ['Admin', 'Creator', 'Learner'],
      token:   'mock-jwt-admin',
      idToken: 'mock-id-admin',
    },
  },
  'creator@ai-tutor.local': {
    password: 'Creator@123',
    user: {
      id:      'cccccccc-0002-0000-0000-000000000002',
      name:    'Chris Creator',
      email:   'creator@ai-tutor.local',
      roles:   ['Creator', 'Learner'],
      token:   'mock-jwt-creator',
      idToken: 'mock-id-creator',
    },
  },
  'learner@ai-tutor.local': {
    password: 'Learner@123',
    user: {
      id:      'dddddddd-0003-0000-0000-000000000003',
      name:    'Leah Learner',
      email:   'learner@ai-tutor.local',
      roles:   ['Learner'],
      token:   'mock-jwt-learner',
      idToken: 'mock-id-learner',
    },
  },
};

// ── Public API ────────────────────────────────────────────────────────────────

// Stores the logged-in user's email across page refreshes within the same tab.
const MOCK_SESSION_KEY = 'ai_tutor_mock_user_email';

function restoreMockUser(): AuthUser | null {
  if (!AUTH_MOCK) return null;
  const email = sessionStorage.getItem(MOCK_SESSION_KEY);
  if (!email) return null;
  // Check hardcoded credentials first, then cached registered-user data
  if (MOCK_CREDENTIALS[email]) return MOCK_CREDENTIALS[email].user;
  const cached = sessionStorage.getItem(`ai_tutor_reg_user_${email}`);
  return cached ? (JSON.parse(cached) as AuthUser) : null;
}

// Start logged-out — require an explicit login. Restore session on page refresh.
let _mockUser: AuthUser | null = restoreMockUser();

export const authService = {
  /**
   * Initialise Keycloak with PKCE flow.
   * Returns the authenticated user, or null when running in mock mode.
   * In dev mode, falls back to the mock user if Keycloak is unreachable.
   */
  async init(): Promise<AuthUser | null> {
    if (AUTH_MOCK) return _mockUser;

    try {
      const instance = getInstance();
      const authenticated = await instance.init({
        onLoad:           'check-sso',
        silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
        pkceMethod:       'S256',
        checkLoginIframe: false,
      });

      if (!authenticated) return null;

      // Periodic token refresh
      instance.onTokenExpired = () => {
        instance.updateToken(TOKEN_MIN_VALIDITY_SECONDS).catch(() => {
          console.warn('[Keycloak] Token refresh failed — logging out');
          instance.logout();
        });
      };

      return parseClaims(instance);
    } catch {
      // Keycloak is unreachable — return null so the login page is shown.
      // Users can sign in with demo credentials when VITE_AUTH_MOCK is false but
      // Keycloak is not reachable (e.g. running the frontend standalone in dev).
      console.warn('[Keycloak] Unreachable — returning null, please log in explicitly.');
      return null;
    }
  },

  /** Sign in with email + password (mock) or redirect to Keycloak (real). */
  async login(email?: string, password?: string): Promise<void> {
    if (AUTH_MOCK) {
      if (!email || !password) throw new Error('Email and password are required.');
      const emailKey = email.toLowerCase().trim();
      const entry = MOCK_CREDENTIALS[emailKey];
      if (entry) {
        if (entry.password !== password) throw new Error('Invalid email or password.');
        _mockUser = entry.user;
        sessionStorage.setItem(MOCK_SESSION_KEY, emailKey);
        return;
      }
      // Fall back to backend for self-registered users
      const res = await fetch('/api/v1/auth/mock-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailKey, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({})) as { detail?: string };
        throw new Error(err.detail ?? 'Invalid email or password.');
      }
      const data = await res.json() as {
        token: string; user_id: string; roles: string[]; approval_status: string; full_name: string;
      };
      if (data.approval_status !== 'approved') {
        throw new Error('Your account is pending admin approval. Please try again later.');
      }
      _mockUser = {
        id:      data.user_id,
        name:    data.full_name,
        email:   emailKey,
        roles:   data.roles,
        token:   data.token,
        idToken: data.token,
      };
      sessionStorage.setItem(MOCK_SESSION_KEY, emailKey);
      sessionStorage.setItem(`ai_tutor_reg_user_${emailKey}`, JSON.stringify(_mockUser));
      return;
    }
    // Dev fallback: if Keycloak is unreachable, use admin mock.
    if (import.meta.env.DEV) {
      try {
        await getInstance().login({ redirectUri: window.location.href });
      } catch {
        _mockUser = MOCK_CREDENTIALS['admin@ai-tutor.local'].user;
        sessionStorage.setItem(MOCK_SESSION_KEY, 'admin@ai-tutor.local');
      }
      return;
    }
    await getInstance().login({ redirectUri: window.location.href });
  },

  /** Logout and redirect to Keycloak. */
  async logout(): Promise<void> {
    if (AUTH_MOCK) {
      _mockUser = null;
      sessionStorage.removeItem(MOCK_SESSION_KEY);
      return;
    }
    await getInstance().logout({ redirectUri: window.location.origin });
  },

  /** Return the currently authenticated user (sync, from cached token). */
  getUser(): AuthUser | null {
    if (AUTH_MOCK) return _mockUser;
    const instance = kc;
    if (!instance?.authenticated) return null;
    return parseClaims(instance);
  },

  /**
   * Return a fresh, valid access token, proactively refreshing if needed.
   * Use this when attaching Authorization headers to API calls.
   */
  async getToken(): Promise<string> {
    if (AUTH_MOCK) return _mockUser?.token ?? '';
    const instance = getInstance();
    await instance.updateToken(TOKEN_MIN_VALIDITY_SECONDS);
    return instance.token ?? '';
  },

  hasRole(role: string): boolean {
    return this.getUser()?.roles.includes(role) ?? false;
  },
};
