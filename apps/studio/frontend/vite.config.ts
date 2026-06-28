import path from 'node:path'
import { configDefaults, defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
// Sidecar proxy target: STUDIO_SIDECAR_PORT pinpoints the real sidecar port so the
// dev tunnel proxy (browser → 127.0.0.1:5173/api → vite → sidecar) lines up with
// the dynamic port Tauri's sidecar binds to. Resolution order, highest priority
// first: shell env (set by launcher), then apps/studio/frontend/.env.local (vite
// loadEnv). Fallback 8787 is the legacy default and a clear "you forgot to set
// the port" signal (R-F2).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, ['STUDIO_', 'VITE_'])
  const sidecarPort = process.env.STUDIO_SIDECAR_PORT ?? env.STUDIO_SIDECAR_PORT ?? '8787'
  const sidecarHttpTarget = `http://127.0.0.1:${sidecarPort}`
  const sidecarWsTarget = `ws://127.0.0.1:${sidecarPort}`
  // Surface the resolved port so misalignments are obvious in vite startup logs.
  // eslint-disable-next-line no-console
  console.log(`[vite] proxy /api -> ${sidecarHttpTarget}  (STUDIO_SIDECAR_PORT=${sidecarPort})`)
  return {
  cacheDir: process.env.VITE_CACHE_DIR ?? 'node_modules/.vite',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    dedupe: ['react', 'react-dom'],
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
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    warmup: {
      clientFiles: ['./src/main.tsx'],
    },
    proxy: {
      // Dev tunnel mode uses same-origin browser URLs and lets Vite forward to backend.
      // Targets follow STUDIO_SIDECAR_PORT so the proxy tracks Tauri's dynamic sidecar
      // port instead of the legacy 8787 default (R-F2).
      '/api': {
        target: sidecarHttpTarget,
        changeOrigin: false,
        ws: true,
      },
      '/ws': {
        target: sidecarWsTarget,
        ws: true,
        changeOrigin: false,
      },
    },
    allowedHosts: ['.trycloudflare.com', 'localhost', '127.0.0.1', '144.202.108.83'],
  },
  test: {
    exclude: [...configDefaults.exclude, 'tests/e2e/**'],
  },
  }
})
