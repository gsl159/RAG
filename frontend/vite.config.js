import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{js,ts}'],
  },
  resolve: {
    alias: { '@': resolve(__dirname, 'src') }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api/ws': {
        target:       'http://localhost:8000',
        changeOrigin: true,
        ws:           true,
        rewrite:      path => path.replace(/^\/api/, ''),
      },
      '/api': {
        target:       'http://localhost:8000',
        changeOrigin: true,
        rewrite:      path => path.replace(/^\/api/, ''),
      }
    }
  }
})
