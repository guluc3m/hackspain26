// T36 — Remotion v2: ANUNCIO de la app con capturas reales y animaciones.
// Misma estética Typst (theme.ts + fuentes) y el mismo feed de datos.
import React from "react";
import {
  AbsoluteFill, interpolate, Sequence, staticFile, useCurrentFrame,
} from "remotion";
import { Chip, Titulo } from "./Secciones";
import { BROWN, GOLD, INK, ORANGE, PAPER, RED, SAND, SLATE, TEAL } from "./theme";
import type { Datos } from "./datos";

const CAPTURA = (n: string) => staticFile(`capturas/${n}.png`);

// ------------------------------------------------------------ primitivas

const Zoom: React.FC<{ src: string; titulo: string; pie: string; dur: number }> = ({
  src, titulo, pie, dur,
}) => {
  const frame = useCurrentFrame();
  const entra = interpolate(frame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const escala = interpolate(frame, [0, dur - 10], [1.0, 1.12], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const panX = interpolate(frame, [0, dur - 10], [-20, 20], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const sale = interpolate(frame, [dur - 10, dur], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ opacity: Math.min(entra, sale), background: PAPER }}>
      <div style={{ padding: "40px 0 0 90px", fontFamily: "Bungee", fontSize: 40, color: INK }}>
        {titulo}
      </div>
      <div style={{ padding: "18px 90px", height: 900, overflow: "hidden" }}>
        <img
          src={src}
          style={{
            width: "100%", transform: `scale(${escala}) translateX(${panX}px)`,
            transformOrigin: "top left", borderRadius: 12,
            border: `4px solid ${BROWN}`, boxShadow: "0 10px 30px rgba(42,23,15,0.35)",
          }}
        />
      </div>
      <div style={{ padding: "0 90px", fontFamily: "'DM Sans'", fontSize: 28, color: BROWN, fontStyle: "italic" }}>
        {pie}
      </div>
    </AbsoluteFill>
  );
};

const Frase: React.FC<{ lineas: string[]; acento?: string }> = ({ lineas, acento = GOLD }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{
      background: INK, alignItems: "center", justifyContent: "center",
      flexDirection: "column", padding: "0 160px", textAlign: "center",
    }}>
      <div style={{ width: 120, height: 8, background: acento, marginBottom: 40 }} />
      {lineas.map((l, i) => (
        <div key={i} style={{
          opacity: interpolate(frame - i * 12, [0, 10], [0, 1], {
            extrapolateLeft: "clamp", extrapolateRight: "clamp",
          }),
          fontFamily: i === 0 ? "Bungee" : "'DM Sans'",
          fontSize: i === 0 ? 74 : 44,
          color: i === 0 ? PAPER : "#e8dcc4",
          margin: "14px 0",
        }}>{l}</div>
      ))}
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------ escalera animada

const Ramas: React.FC<{ datos: Datos }> = ({ datos }) => {
  const frame = useCurrentFrame();
  const e = datos.escalera;
  const texto = Number(e.texto_usable.valor);
  const total = 500;
  const pct = (n: number) => `${Math.round((n / total) * 100)} %`;
  const ramas: [string, string, string, number][] = [
    ["capa de texto", `rung 1 · ${texto} (${pct(texto)})`, String(GOLD), 30],
    ["raster + OCR", `rung 2-3 · ${e.raster.valor} (${pct(Number(e.raster.valor))})`, String(TEAL), 46],
    ["solo QR", `rung 2 · ${e.solo_qr.valor} (${pct(Number(e.solo_qr.valor))})`, String(SLATE), 62],
  ];
  return (
    <AbsoluteFill style={{ background: PAPER, padding: "60px 110px" }}>
      <div style={{ fontFamily: "Bungee", fontSize: 46, color: INK }}>
        Un PDF entra. La escalera decide, POR PÁGINA.
      </div>
      {/* el PDF entra */}
      <div style={{
        opacity: interpolate(frame, [5, 18], [0, 1], { extrapolateRight: "clamp" }),
        margin: "34px 0 10px",
        display: "inline-block", fontFamily: "Bungee", fontSize: 34,
        color: PAPER, background: INK, borderRadius: 10, padding: "14px 28px",
      }}>
        factura.pdf
      </div>
      {/* las tres ramas con sus % medidos */}
      {ramas.map(([titulo, dato, color, delay]) => {
        const op = interpolate(frame - delay, [0, 12], [0, 1], {
          extrapolateLeft: "clamp", extrapolateRight: "clamp",
        });
        return (
          <div key={titulo} style={{
            opacity: op, display: "flex", alignItems: "center", gap: 20,
            margin: "16px 0",
          }}>
            <div style={{ width: 60, height: 8, background: color, borderRadius: 4 }} />
            <div style={{ fontFamily: "'DM Sans'", fontSize: 32, color: INK, minWidth: 300 }}>
              {titulo}
            </div>
            <div style={{ fontFamily: "Bungee", fontSize: 36, color }}>{dato}</div>
          </div>
        );
      })}
      {/* rungs 4 y 5 */}
      <div style={{
        marginTop: 30, opacity: interpolate(frame - 78, [0, 12], [0, 1], {
          extrapolateLeft: "clamp", extrapolateRight: "clamp",
        }),
      }}>
        <div style={{ fontFamily: "'DM Sans'", fontSize: 30, color: INK }}>
          y las páginas difíciles: <b>rung 4</b> (PaddleOCR-VL local, serializado)
          → <b>rung 5</b> deepseek, solo lectura candidata.
        </div>
        <div style={{ fontFamily: "'DM Sans'", fontSize: 28, color: BROWN, marginTop: 14 }}>
          rung 1: 0.4 ms media · p95 2.0 ms — rung 2: 42.1 ms · p95 73.0 ms (medido)
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------ timeline traza

const Paso: React.FC<{ paso: string; detalle: string; acento: string; delay: number; total: number }> = ({
  paso, detalle, acento, delay, total,
}) => {
  const frame = useCurrentFrame();
  const op = interpolate(frame - delay, [0, 10], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const ancho = interpolate(frame - delay, [0, 10], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <div style={{ opacity: op, flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
      {delay > 0 && (
        <div style={{ height: 6, background: SAND, borderRadius: 3 }}>
          <div style={{ height: 6, width: `${ancho * 100}%`, background: acento, borderRadius: 3 }} />
        </div>
      )}
      <div style={{ fontFamily: "Bungee", fontSize: 28, color: acento }}>{paso}</div>
      <div style={{ fontFamily: "'DM Sans'", fontSize: 25, color: INK, lineHeight: 1.3 }}>
        {detalle}
      </div>
    </div>
  );
};

const TrazaAnimada: React.FC<{ datos: Datos }> = ({ datos }) => {
  const t = datos.traza;
  if (!t.disponible) {
    return <AbsoluteFill style={{ background: PAPER }} />;
  }
  const pasos: [string, string, string][] = [
    ["1 · PDF", `${t.file_id ?? ""}\nsha ${String(t.sha256).slice(0, 8)}…`, GOLD],
    ["2 · rungs", (t.rungs ?? []).join(" · "), TEAL],
    ["3 · campos", (t.campos_parseados ?? []).slice(0, 6).join(", "), ORANGE],
    ["4 · reglas", `${(t.reglas ?? []).length} veredictos con candidato elegido`, SLATE],
    ["5 · decisión", String(t.resultado ?? ""), RED],
  ];
  return (
    <AbsoluteFill style={{ background: PAPER, padding: "70px 90px" }}>
      <div style={{ fontFamily: "Bungee", fontSize: 44, color: INK, marginBottom: 40 }}>
        Cada factura deja rastro completo.
      </div>
      <div style={{ display: "flex", gap: 26, marginTop: 30 }}>
        {pasos.map(([paso, detalle, color], i) => (
          <Paso key={paso} paso={paso} detalle={detalle} acento={color}
            delay={i * 14} total={5} />
        ))}
      </div>
      <div style={{ marginTop: 60, fontFamily: "'DM Sans'", fontSize: 28, color: BROWN, fontStyle: "italic" }}>
        ledger SQLite + JSONL append-only · cache (sha256, rung, versión, config) · reprocesable desde cualquier punto
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------ composición

export const Anuncio: React.FC<{ datos: Datos }> = ({ datos }) => {
  const n = datos.numeros;
  const dist = String((n.distribucion_final as { valor: string }).valor);
  const [pagar, resto] = dist.split(" · ");
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      {/* 1 · el problema de Alberto (0–9 s) */}
      <Sequence from={0} durationInFrames={270}>
        <Frase lineas={[
          "Alberto paga facturas con 4 reglas.",
          "500 PDFs. Trampas por todas partes:",
          "proveedores fantasma, duplicados,",
          "instrucciones escondidas. ¿Qué paga hoy?",
        ]} />
      </Sequence>

      {/* 2 · la app, con capturas reales (9–49 s) */}
      <Sequence from={270} durationInFrames={240}>
        <Zoom src={CAPTURA("inicio")} titulo="¿Qué pago hoy?" dur={240}
          pie="El resumen de Alberto: pagos, no-pagos con motivo en llano, y los escalados por dinero en riesgo." />
      </Sequence>
      <Sequence from={510} durationInFrames={200}>
        <Zoom src={CAPTURA("facturas")} titulo="Cada factura, su veredicto" dur={200}
          pie="Resultado, reglas que decidieron, evidencia, extractor y latencia — todo en una fila." />
      </Sequence>
      <Sequence from={710} durationInFrames={240}>
        <Zoom src={CAPTURA("revision")} titulo="Revisar con calma" dur={240}
          pie="Cola de escalados: página y lecturas lado a lado. Resolver con calma; el lote nunca espera." />
      </Sequence>
      <Sequence from={950} durationInFrames={200}>
        <Zoom src={CAPTURA("reglas")} titulo="Reglas que se ven" dur={200}
          pie="El set activo, los umbrales y el «qué pasaría si…» — la v4 llegará como DATOS." />
      </Sequence>
      <Sequence from={1150} durationInFrames={200}>
        <Zoom src={CAPTURA("salud")} titulo="Salud del sistema" dur={200}
          pie="Fallos de proveedor, reintentos, estado degradado: si llama-server cae, se ve." />
      </Sequence>

      {/* 3 · escalera animada (49–58 s) */}
      <Sequence from={1350} durationInFrames={270}>
        <Ramas datos={datos} />
      </Sequence>

      {/* 4 · timeline de una factura real (58–67 s) */}
      <Sequence from={1620} durationInFrames={270}>
        <TrazaAnimada datos={datos} />
      </Sequence>

      {/* 5 · resultados (67–75 s) */}
      <Sequence from={1890} durationInFrames={240}>
        <AbsoluteFill style={{
          background: PAPER, alignItems: "center", justifyContent: "center",
          flexDirection: "column", padding: "0 120px",
        }}>
          <div style={{ fontFamily: "Bungee", fontSize: 64, color: INK, marginBottom: 40 }}>
            El resultado, medido:
          </div>
          <div style={{ display: "flex", gap: 30 }}>
            <div style={{ background: SAND, borderRadius: 16, padding: "30px 44px", borderTop: `10px solid ${GOLD}` }}>
              <div style={{ fontFamily: "Bungee", fontSize: 66, color: INK }}>
                {pagar.replace("PAGAR ", "")}
              </div>
              <div style={{ fontFamily: "'DM Sans'", fontSize: 26, color: BROWN }}>pagadas con reglas en verde</div>
            </div>
            <div style={{ background: SAND, borderRadius: 16, padding: "30px 44px", borderTop: `10px solid ${TEAL}` }}>
              <div style={{ fontFamily: "Bungee", fontSize: 66, color: INK }}>500/500</div>
              <div style={{ fontFamily: "'DM Sans'", fontSize: 26, color: BROWN }}>validadas contra los PDF exactos</div>
            </div>
            <div style={{ background: SAND, borderRadius: 16, padding: "30px 44px", borderTop: `10px solid ${ORANGE}` }}>
              <div style={{ fontFamily: "Bungee", fontSize: 66, color: INK }}>0.00 €</div>
              <div style={{ fontFamily: "'DM Sans'", fontSize: 26, color: BROWN }}>coste cloud del lote 1</div>
            </div>
          </div>
          <div style={{ marginTop: 36, fontFamily: "'DM Sans'", fontSize: 30, color: SLATE }}>
            {resto} — y cada escalado llega con la página y las lecturas, listo para revisar.
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* 6 · cierre (75–90 s) */}
      <Sequence from={2130} durationInFrames={270}>
        <AbsoluteFill style={{
          background: INK, alignItems: "center", justifyContent: "center",
          flexDirection: "column", padding: "0 140px",
        }}>
          <div style={{ fontFamily: "Bungee", fontSize: 70, color: PAPER, marginBottom: 30 }}>
            La entrega, lista.
          </div>
          {datos.cierre.entregables.map((e, i) => (
            <div key={e} style={{
              opacity: interpolate(i * 12 + 20, [0, 10], [0.3, 1], {
                extrapolateLeft: "clamp", extrapolateRight: "clamp",
              }),
              fontFamily: "'DM Sans'", fontSize: 38, color: "#e8dcc4", margin: "10px 0",
            }}>
              ✓ {e}
            </div>
          ))}
          <div style={{ marginTop: 30, fontFamily: "Bungee", fontSize: 34, color: GOLD }}>
            y la app de Alberto: un paso para abrir.
          </div>
        </AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  );
};
