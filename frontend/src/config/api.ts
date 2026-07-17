/**
 * Relative API paths — no hardcoded host.
 *
 * In development (Vite dev server on :3000) requests go through the Vite proxy
 * which forwards /api/* → http://nginx:80, avoiding CORS entirely.
 *
 * In production (Nginx serves the built frontend) requests go to the same
 * origin and Nginx proxies them to the correct backend services.
 */
export const API_BASE = '';

export const CHAT_API    = `${API_BASE}/api/v1/chat`;
export const KB_API      = `${API_BASE}/api/v1/knowledge-bases`;
export const CONTENT_API = `${API_BASE}/api/v1/content`;
export const ADMIN_API   = `${API_BASE}/api/v1/admin`;
export const LLM_API     = `${API_BASE}/api/internal/llm`;
export const RAG_API     = `${API_BASE}/api/internal/rag`;
