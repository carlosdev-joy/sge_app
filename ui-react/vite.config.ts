import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// base '/' — nginx serve o SPA direto da raiz (/usr/share/nginx/html)
// sem sub-path prefix. Referências a /assets/... funcionam diretamente.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: { outDir: 'dist', emptyOutDir: true },
})
