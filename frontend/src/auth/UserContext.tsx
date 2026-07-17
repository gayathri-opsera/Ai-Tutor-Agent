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

// ── Context ───────────────────────────────────────────────────────────────────

interface UserContextValue {
  user:         AppUser | null;
  initializing: boolean;
  login:        () => Promise<void>;
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
    authService.init().then(authUser => {
      if (authUser) setUser(fromAuthUser(authUser));
    }).catch(err => {
      console.error('[UserContext] Keycloak init failed:', err);
    }).finally(() => setInitializing(false));
  }, []);

  const login = useCallback(async () => {
    await authService.login();
    // After redirect, init() will re-run on page load.
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
