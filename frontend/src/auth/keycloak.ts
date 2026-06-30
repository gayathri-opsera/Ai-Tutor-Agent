export interface AuthUser {
  id: string;
  roles: string[];
  token: string;
}

let currentUser: AuthUser | null = {
  id: 'demo-user',
  roles: ['Learner', 'Creator', 'Admin'],
  token: 'demo-token',
};

export const authService = {
  init: async () => currentUser,
  login: async () => currentUser,
  logout: async () => { currentUser = null; },
  getUser: () => currentUser,
  hasRole: (role: string) => currentUser?.roles.includes(role) ?? false,
};
