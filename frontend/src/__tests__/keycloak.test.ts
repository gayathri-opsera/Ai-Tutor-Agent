/**
 * Unit tests for keycloak.ts auth service (mock mode).
 *
 * When VITE_AUTH_MOCK=true the authService uses a static mock user,
 * allowing these tests to run without a live Keycloak instance.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Set mock mode before importing the module
vi.stubEnv('VITE_AUTH_MOCK', 'true');

const { authService } = await import('../../auth/keycloak');

describe('authService (mock mode)', () => {
  it('init() resolves with a mock AuthUser', async () => {
    const user = await authService.init();
    expect(user).not.toBeNull();
    expect(user?.roles).toContain('Admin');
    expect(user?.token).toBe('mock-jwt-token');
  });

  it('getUser() returns the mock user synchronously after init', async () => {
    await authService.init();
    const user = authService.getUser();
    expect(user?.id).toBeTruthy();
    expect(user?.name).toContain('Mock');
  });

  it('hasRole() returns true for existing roles', async () => {
    await authService.init();
    expect(authService.hasRole('Admin')).toBe(true);
    expect(authService.hasRole('Learner')).toBe(true);
  });

  it('hasRole() returns false for non-assigned roles', async () => {
    await authService.init();
    expect(authService.hasRole('SuperAdmin')).toBe(false);
  });

  it('getToken() returns mock token without network calls', async () => {
    const token = await authService.getToken();
    expect(token).toBe('mock-jwt-token');
  });

  it('logout() clears the user', async () => {
    await authService.init();
    await authService.logout();
    expect(authService.getUser()).toBeNull();
  });

  it('login() reinstates the mock user', async () => {
    await authService.logout();
    await authService.login();
    expect(authService.getUser()).not.toBeNull();
  });
});
