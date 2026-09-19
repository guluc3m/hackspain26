// Datos desde presentation/public/datos.json — generado por
// `uv run python -m albertitos.presentacion` desde .sdd/metrics/.
// NADA hardcodeado: cada cifra llega con su etiqueta (medido/estimado).
import { staticFile } from "remotion";

export type Metrica = { valor: unknown; etiqueta: string };

export type Datos = {
  generado: string;
  portada: { titulo: string; subtitulo: string; chips: string[] };
  problema: {
    n_facturas: Metrica;
    n_resultados: Metrica;
    resultados: string[];
    norma: string;
  };
  escalera: {
    texto_usable: Metrica;
    raster: Metrica;
    solo_qr: Metrica;
    errores_timeouts: Metrica;
    rung4: string;
    rung5: string;
    latencias: Record<
      string,
      { media: Metrica; p95: Metrica }
    >;
  };
  decisiones: { titulo: string; porque: string; evidencia: string }[];
  numeros: Record<string, Metrica | { nucleos: Metrica; ram: Metrica }>;
  traza: {
    disponible: boolean;
    file_id?: string;
    sha256?: string;
    rungs?: string[];
    campos_parseados?: string[];
    reglas?: string[];
    resultado?: string;
  };
  cierre: { entregables: string[]; bonus: string };
};

export const DATOS_URL = staticFile("datos.json");
