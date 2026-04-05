import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5283,
    proxy: {
      '/api': {
        target: 'http://localhost:5183',
        changeOrigin: true,
      },
    },
  },
})
