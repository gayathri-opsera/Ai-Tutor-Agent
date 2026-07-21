import {
  createContext, useContext, useState, useEffect, useCallback, ReactNode,
} from 'react';
import { authService, type AuthUser } from './keycloak';

// ── AppUser ───────────────────────────────────────────────────────────────────

export interface AppUser {
  id:          string;
  name:        string;
  email:       string;
  /** All application roles granted via Keycloak realm roles. */
  roles:       string[];
  /** Convenience: true when the user holds the 'Admin' or 'SuperAdmin' role. */
  isAdmin:     boolean;
  /** Convenience: true when the user holds the 'Creator' role. */
  isCreator:   boolean;
  avatar:      string;
  keycloak_id: string;
  /** Whether the user has been approved by an admin (null = unknown/loading). */
  approvalStatus: 'pending' | 'approved' | 'rejected' | null;
}

function fromAuthUser(u: AuthUser): AppUser {
  return {
    id:             u.id,
    name:           u.name,
    email:          u.email,
    roles:          u.roles,
    isAdmin:        u.roles.some(r => r === 'Admin' || r === 'SuperAdmin'),
    isCreator:      u.roles.includes('Creator'),
    avatar:         '👤',
    keycloak_id:    u.id,
    approvalStatus: null,
  };
}

/**
 * Register (or re-register) the authenticated user on the backend and return
 * their current approval_status.  Safe to call on every login — the endpoint
 * is idempotent.  Returns 'approved' as a safe default on any network error so
 * mock-auth users (whose tokens are not real JWTs) are never gated.
 */
async function fetchApprovalStatus(user: AppUser, token: string): Promise<'pending' | 'approved' | 'rejected'> {
  // Mock tokens are not real JWTs — skip the backend call; mock users are pre-seeded as approved.
  if (!token || token.startsWith('mock-jwt')) return 'approved';

  try {
    const resp = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ email: user.email, full_name: user.name }),
    });
    if (resp.ok) {
      const data = await resp.json() as { approval_status?: string };
      return (data.approval_status ?? 'approved') as 'pending' | 'approved' | 'rejected';
    }
  } catch {
    // Network unavailable (e.g. admin-config not running) — fail open
  }
  return 'approved';
}

// ── Context ───────────────────────────────────────────────────────────────────

interface UserContextValue {
  user:         AppUser | null;
  initializing: boolean;
  login:        (email: string, password: string) => Promise<void>;
  logout:       () => Promise<void>;
  /** @deprecated — kept for backward compatibility during migration. */
  switchUser:   (u: AppUser) => void;
  getToken:     () => Promise<string>;
}

const UserContext = createContext<UserContextValue>({
  user: null,
  initializing: true,
  login: async () => {},
  logout: async () => {},
  switchUser: () => {},
  getToken: async () => '',
});

// ── Provider ──────────────────────────────────────────────────────────────────

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser]                 = useState<AppUser | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    authService.init().then(async authUser => {
      if (authUser) {
        const appUser = fromAuthUser(authUser);
        const token = await authService.getToken();
        appUser.approvalStatus = await fetchApprovalStatus(appUser, token);
        setUser(appUser);
      }
    }).catch(err => {
      console.error('[UserContext] Keycloak init failed:', err);
    }).finally(() => setInitializing(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await authService.login(email, password);
    // For real Keycloak a page redirect happens and init() re-runs on reload.
    // For mock/dev mode login() returns immediately — re-initialize here to update state.
    const authUser = await authService.init();
    if (authUser) {
      const appUser = fromAuthUser(authUser);
      const token = await authService.getToken();
      appUser.approvalStatus = await fetchApprovalStatus(appUser, token);
      setUser(appUser);
    }
  }, []);

  const logout = useCallback(async () => {
    setUser(null);
    await authService.logout();
  }, []);

  const switchUser = useCallback((u: AppUser) => {
    // In production, switching users requires logging out and re-authenticating.
    // This shim preserves backward-compat for any code that still calls it.
    setUser(u);
  }, []);

  const getToken = useCallback(() => authService.getToken(), []);

  return (
    <UserContext.Provider value={{ user, initializing, login, logout, switchUser, getToken }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() { return useContext(UserContext); }
