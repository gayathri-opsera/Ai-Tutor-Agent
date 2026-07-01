import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export interface AppUser {
  id:          string;
  name:        string;
  email:       string;
  role:        'Learner' | 'Creator' | 'Admin';
  avatar:      string;
  keycloak_id: string;
}

export const DEMO_USERS: AppUser[] = [
  {
    id:          'aaaaaaaa-0003-0000-0000-000000000003',
    name:        'Carol Learner',
    email:       'learner@ai-tutor.local',
    role:        'Learner',
    avatar:      '🎓',
    keycloak_id: 'keycloak-learner-003',
  },
  {
    id:          'aaaaaaaa-0002-0000-0000-000000000002',
    name:        'Bob Creator',
    email:       'creator@ai-tutor.local',
    role:        'Creator',
    avatar:      '✏️',
    keycloak_id: 'keycloak-creator-002',
  },
  {
    id:          'aaaaaaaa-0001-0000-0000-000000000001',
    name:        'Alice Admin',
    email:       'admin@ai-tutor.local',
    role:        'Admin',
    avatar:      '🛡️',
    keycloak_id: 'keycloak-admin-001',
  },
];

interface UserContextValue {
  user:        AppUser | null;
  login:       (u: AppUser) => void;
  logout:      () => void;
  switchUser:  (u: AppUser) => void;
}

const UserContext = createContext<UserContextValue>({
  user: null, login: () => {}, logout: () => {}, switchUser: () => {},
});

const STORAGE_KEY = 'ai_tutor_user_id';

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return DEMO_USERS.find(u => u.id === saved) ?? null;
  });

  const login     = (u: AppUser) => { setUser(u); localStorage.setItem(STORAGE_KEY, u.id); };
  const logout    = () => { setUser(null); localStorage.removeItem(STORAGE_KEY); };
  const switchUser = (u: AppUser) => login(u);

  return (
    <UserContext.Provider value={{ user, login, logout, switchUser }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() { return useContext(UserContext); }
