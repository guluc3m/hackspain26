import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev proxy; production and desktop are served by the same local FastAPI.
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } }
})
