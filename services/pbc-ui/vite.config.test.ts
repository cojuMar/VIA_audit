import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Test config — proxies API calls directly to running pbc-service on port 3018
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5191,
    proxy: {
      '/api': {
        target: 'http://localhost:3018',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
