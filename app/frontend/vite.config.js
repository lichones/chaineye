import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: false,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('cytoscape') || id.includes('react-cytoscapejs')) {
            return 'cytoscape'
          }
          if (id.includes('/react/') || id.includes('/react-dom/')) {
            return 'react'
          }
        },
      },
    },
  },
})
