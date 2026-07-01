import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],

  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      // Forward all /api calls to Nginx (avoids cross-origin issues in dev)
      '/api': {
        target: 'http://nginx:80',
        changeOrigin: true,
        secure: false,
        // Required for SSE (Server-Sent Events) streaming to work through Vite
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Accept-Encoding', 'identity');
          });
        },
      },
    },
  },

  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
