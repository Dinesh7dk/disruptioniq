import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://127.0.0.1:8000',
      '/me': 'http://127.0.0.1:8000',
      '/disruptions': 'http://127.0.0.1:8000',
      '/webhooks': 'http://127.0.0.1:8000',
      '/import': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000'
    }
  }
})
