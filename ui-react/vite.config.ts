import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// base '/v2/' — o app React é servido num sub-path, ao lado da UI legada (raiz).
// Migração incremental: só as telas marcadas como migradas são roteadas aqui.
export default defineConfig({
  plugins: [react()],
  base: '/v2/',
  build: { outDir: 'dist', emptyOutDir: true },
})
