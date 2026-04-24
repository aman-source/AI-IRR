import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:9200',
      '/health': 'http://localhost:9200',
    },
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
})
