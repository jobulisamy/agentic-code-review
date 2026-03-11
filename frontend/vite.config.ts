import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',       // Bind to all interfaces — required inside Docker
    port: 5173,
    watch: {
      usePolling: true,     // Required on macOS + Docker volume mounts (inotify doesn't work)
    },
    hmr: {
      clientPort: 5173,     // Must match the exposed Docker host port
    },
  },
})
