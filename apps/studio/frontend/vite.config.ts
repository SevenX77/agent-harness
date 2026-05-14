import path from 'node:path'
import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  cacheDir: process.env.VITE_CACHE_DIR ?? 'node_modules/.vite',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/monaco-editor') || id.includes('node_modules/@monaco-editor')) {
            return 'monaco'
          }
          if (id.includes('node_modules/@xyflow') || id.includes('node_modules/reactflow')) {
            return 'graph'
          }
          if (id.includes('node_modules/react-markdown')) {
            return 'markdown'
          }
          if (id.includes('node_modules/xterm')) {
            return 'terminal'
          }
          if (id.includes('src/components/copilot') || id.includes('src/hooks/useCopilot')) {
            return 'copilot'
          }
          if (id.includes('src/components/diff') || id.includes('src/hooks/useGoldenDiff')) {
            return 'diff'
          }
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) {
            return 'react'
          }
          if (id.includes('node_modules')) {
            return 'vendor'
          }
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    warmup: {
      clientFiles: ['./src/main.tsx'],
    },
    proxy: {
      // Dev tunnel mode uses same-origin browser URLs and lets Vite forward to backend.
      '/api': {
        target: 'http://127.0.0.1:8787',
        changeOrigin: false,
        ws: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8787',
        ws: true,
        changeOrigin: false,
      },
    },
    allowedHosts: ['.trycloudflare.com', 'localhost', '127.0.0.1'],
  },
  test: {
    exclude: [...configDefaults.exclude, 'tests/e2e/**'],
  },
})
