// Fuentes HEREDADAS del informe Typst (docs/report/fonts/): Bungee + DM Sans.
import { continueRender, delayRender, staticFile } from "remotion";

let listo = false;

export const cargarFuentes = (): number => {
  if (listo) return 0;
  const handle = delayRender("cargando Bungee + DM Sans (docs/report/fonts)");
  const carga = async (): Promise<void> => {
    const bungee = new FontFace(
      "Bungee",
      `url(${staticFile("fonts/Bungee-Regular.ttf")})`
    );
    const sans = new FontFace(
      "DM Sans",
      `url(${staticFile("fonts/DMSans.ttf")})`
    );
    const sansItalic = new FontFace(
      "DM Sans",
      `url(${staticFile("fonts/DMSans-Italic.ttf")})`,
      { style: "italic" }
    );
    for (const f of [bungee, sans, sansItalic]) {
      await f.load();
      document.fonts.add(f);
    }
  };
  void carga()
    .catch((e) => {
      // si una fuente falla, seguimos con la de sistema (el vídeo sale igual)
      console.warn("fuente no cargada:", e);
    })
    .finally(() => {
      listo = true;
      continueRender(handle);
    });
  return handle;
};
