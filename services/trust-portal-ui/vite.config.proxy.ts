import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5276,
    proxy: {
      '/api': {
        target: 'http://localhost:5176',
        changeOrigin: true,
      },
    },
  },
})
