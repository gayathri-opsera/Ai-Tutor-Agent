/**
 * Authenticated fetch wrapper.
 *
 * Automatically attaches the current user's bearer token to every request.
 * Falls back to a plain unauthenticated fetch if no token is available
 * (e.g. public endpoints, Keycloak not yet initialised).
 *
 * Usage:
 *   import { apiFetch } from '../config/apiFetch';
 *   const data = await apiFetch('/api/v1/knowledge-bases').then(r => r.json());
 */
import { authService } from '../auth/keycloak';

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  let token = '';
  try {
    token = await authService.getToken();
  } catch {
    // Ignore — will proceed without auth header (e.g. public health checks)
  }

  const headers = new Headers(init?.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  return fetch(input, { ...init, headers });
}
