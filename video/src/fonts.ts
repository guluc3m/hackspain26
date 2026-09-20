import React from 'react';
import { cancelRender, continueRender, delayRender, staticFile } from 'remotion';

// Tipografías reales del producto: los mismos TTFs que sirve la app
// (frontend/public/fonts/) copiados a video/public/fonts/. Se registran a mano
// con un <style> + `document.fonts.load`, sin añadir dependencias
// (@remotion/fonts no está instalado y no se instala).

const FONT_FACES = [
  "@font-face {",
  "  font-family: 'Bungee';",
  `  src: url('${staticFile('fonts/Bungee-Regular.ttf')}') format('truetype');`,
  '  font-weight: 400;',
  '  font-style: normal;',
  '  font-display: block;',
  '}',
  "@font-face {",
  "  font-family: 'DM Sans';",
  `  src: url('${staticFile('fonts/DMSans.ttf')}') format('truetype');`,
  '  font-weight: 100 900;', // DM Sans es un único fichero variable
  '  font-style: normal;',
  '  font-display: block;',
  '}',
].join('\n');

// Especificaciones que se esperan antes del primer frame (los dos tamaños
// reales que usa el vídeo: el número gigante de la portada y el cuerpo).
const READY = ['400 130px Bungee', '400 40px "DM Sans"'] as const;

let injected = false;
const injectFontFaces = (): void => {
  if (injected) return;
  const style = document.createElement('style');
  style.setAttribute('data-filemaid-fonts', '');
  style.textContent = FONT_FACES;
  document.head.appendChild(style);
  injected = true;
};

/**
 * Registra Bungee + DM Sans y bloquea el frame hasta que están cargadas: sin
 * esto, títulos y cuerpo se pintarían con el fallback (Noto Sans).
 */
export const useFonts = (): void => {
  const [handle] = React.useState(() => delayRender('Cargando Bungee + DM Sans'));

  React.useEffect(() => {
    injectFontFaces();
    Promise.all(READY.map((spec) => document.fonts.load(spec)))
      .then(() => {
        const missing = READY.filter((spec) => !document.fonts.check(spec));
        if (missing.length > 0) {
          throw new Error(`Fuentes no disponibles: ${missing.join(', ')}`);
        }
        continueRender(handle);
      })
      .catch((err: Error) => cancelRender(err));
  }, [handle]);
};
