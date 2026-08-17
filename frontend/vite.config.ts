import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/webhook': 'http://localhost:8000',
      '/rules': 'http://localhost:8000',
      '/stats': 'http://localhost:8000',
      '/api': 'http://localhost:8000'
    }
  }
})
