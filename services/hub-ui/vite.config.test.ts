import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Test config — proxies auth and dashboard calls directly to running Docker services
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    proxy: {
      '/auth': {
        target: 'http://localhost:3010',
        changeOrigin: true,
        rewrite: (path) => path, // /auth/login → http://localhost:3010/auth/login
      },
      '/api/dashboard': {
        target: 'http://localhost:3009',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/dashboard/, ''),
      },
    },
  },
});
