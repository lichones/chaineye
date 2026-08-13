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
        manualChunks: {
          cytoscape: ['cytoscape', 'react-cytoscapejs'],
          react: ['react', 'react-dom'],
        },
      },
    },
  },
})
