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

// Tezlik: React va router alohida "vendor" chunk — kod o'zgarganda (har deploy) uning nomi o'zgarmaydi,
// brauzer keshidan olinadi; faqat ilova kodi qayta yuklanadi.
const output = {
  codeSplitting: {
    groups: [
      { name: 'vendor-react', test: /[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/, priority: 20 },
    ],
  },
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  base: process.env.VITE_ELECTRON || mode === 'mobile' ? './' : '/',
  plugins: [react(), mobileBuild(mode)].filter(Boolean),
  build: mode === 'mobile'
    ? {
        outDir: 'dist-mobile',
        emptyOutDir: true,
        rolldownOptions: { input: resolve(__dirname, 'mobile.html'), output },
      }
    : { rolldownOptions: { output } },
}))
