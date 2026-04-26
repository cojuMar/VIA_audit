import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // hub-ui talks to auth-service (`/auth`) for login + notifications and to
    // the dashboard / aggregator (`/api`) for global search. Proxy in dev so
    // cookies and CORS Just Work; in prod nginx fronts the same paths.
    proxy: {
      '/auth': { target: 'http://localhost:8000', changeOrigin: true },
      '/api':  { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
