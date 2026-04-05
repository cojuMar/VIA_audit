import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Test config — proxies auth calls through the running Docker hub-ui nginx on 5173
// which has its own nginx proxy to auth-service inside the Docker network
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    proxy: {
      '/auth': {
        target: 'http://localhost:5173',
        changeOrigin: true,
      },
    },
  },
});
