import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Sin proxy ni conexión real: la conexión con el backend queda vacía
// a propósito. Los targets *_syncth (package.json) ejecutan la UI con
// datos sintéticos de referencia.
//
// base relativa: la ventana nativa (pywebview, src/albertitos/desktop)
// carga frontend/dist/index.html vía file:// y los assets deben resolver
// relativos al HTML.
export default defineConfig({
  base: './',
  plugins: [vue()]
})
