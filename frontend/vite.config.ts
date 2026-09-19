import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Sin proxy ni conexión real: la conexión con el backend queda vacía
// a propósito. Los targets *_syncth (package.json) ejecutan la UI con
// datos sintéticos de referencia.
export default defineConfig({
  plugins: [vue()]
})
