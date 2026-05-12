import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: false,            // use public/manifest.json
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          { urlPattern: /^https:\/\/fonts\.googleapis\.com\//, handler: 'StaleWhileRevalidate', options: { cacheName: 'google-fonts-stylesheets' } },
          { urlPattern: /^https:\/\/fonts\.gstatic\.com\//, handler: 'CacheFirst', options: { cacheName: 'google-fonts-webfonts', expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 } } },
        ]
      }
    }),
  ],
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
