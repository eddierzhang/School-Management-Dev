import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

declare const process: { env: Record<string, string | undefined> }

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    // Same-origin in dev, so the browser never needs CORS and the session cookie
    // is first-party. HR_API_URL points it at an API on another port.
    proxy: { '/api': { target: process.env.HR_API_URL ?? 'http://localhost:8000', changeOrigin: true } },
  },
})
