import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    // Same-origin in dev, so the browser never needs CORS for ordinary use.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
})
