import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The dev server proxies the API and admin to Django so the browser sees one
// origin and the session cookie and CSRF token work exactly as in production.
const backend = process.env.VITE_DEV_BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: backend, changeOrigin: false, xfwd: true },
      '/admin': { target: backend, changeOrigin: false, xfwd: true },
      '/static': { target: backend, changeOrigin: false },
    },
  },
  build: {
    sourcemap: true,
    target: 'es2022',
  },
})
