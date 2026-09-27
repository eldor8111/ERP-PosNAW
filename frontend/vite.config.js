import { renameSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Mobil ilova (E-code Mobile, Capacitor) alohida build: `vite build --mode mobile`
// → dist-mobile/index.html. Dev rejimida http://localhost:5173/mobile.html
const mobileBuild = (mode) => mode === 'mobile' && {
  name: 'mobile-index-html',
  closeBundle() {
    const from = resolve(__dirname, 'dist-mobile/mobile.html')
    if (existsSync(from)) renameSync(from, resolve(__dirname, 'dist-mobile/index.html'))
  },
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  base: process.env.VITE_ELECTRON || mode === 'mobile' ? './' : '/',
  plugins: [react(), mobileBuild(mode)].filter(Boolean),
  ...(mode === 'mobile' && {
    build: {
      outDir: 'dist-mobile',
      emptyOutDir: true,
      rollupOptions: { input: resolve(__dirname, 'mobile.html') },
    },
  }),
}))
