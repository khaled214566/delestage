import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Docker bind-mounts on Windows don't reliably deliver filesystem change
    // events into the Linux container, so Vite's watcher silently misses host
    // edits without polling.
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
