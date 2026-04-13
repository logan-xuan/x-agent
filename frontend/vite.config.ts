import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      host: '0.0.0.0',
      port: parseInt(env.VITE_PORT || '5177'),
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8888',
          changeOrigin: true,
        },
        '/ws': {
          target: env.VITE_WS_URL || 'ws://localhost:8888',
          ws: true,
        },
      },
      // 支持客户端路由 - 所有路由都返回 index.html
      historyApiFallback: true,
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
  }
})
