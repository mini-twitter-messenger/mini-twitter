import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/users': 'http://localhost:80',
      '/tweets': 'http://localhost:80',
      '/timeline': 'http://localhost:80',
    }
  }
})
