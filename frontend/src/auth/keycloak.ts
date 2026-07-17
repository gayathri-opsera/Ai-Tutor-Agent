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

// ── Mock fallback for local dev ────────────────────────────────────────────────

const MOCK_USER: AuthUser = {
  id:      'aaaaaaaa-0001-0000-0000-000000000001',
  name:    'Alice Admin (Mock)',
  email:   'admin@ai-tutor.local',
  roles:   ['Admin', 'Creator', 'Learner'],
  token:   'mock-jwt-token',
  idToken: 'mock-id-token',
};

// ── Public API ────────────────────────────────────────────────────────────────

let _mockUser: AuthUser | null = AUTH_MOCK ? MOCK_USER : null;

export const authService = {
  /**
   * Initialise Keycloak with PKCE flow.
   * Returns the authenticated user, or null when running in mock mode.
   */
  async init(): Promise<AuthUser | null> {
    if (AUTH_MOCK) return _mockUser;

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
  },

  /** Redirect to Keycloak login page. */
  async login(): Promise<void> {
    if (AUTH_MOCK) { _mockUser = MOCK_USER; return; }
    await getInstance().login({ redirectUri: window.location.href });
  },

  /** Logout and redirect to Keycloak. */
  async logout(): Promise<void> {
    if (AUTH_MOCK) { _mockUser = null; return; }
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
    if (AUTH_MOCK) return MOCK_USER.token;
    const instance = getInstance();
    await instance.updateToken(TOKEN_MIN_VALIDITY_SECONDS);
    return instance.token ?? '';
  },

  hasRole(role: string): boolean {
    return this.getUser()?.roles.includes(role) ?? false;
  },
};
