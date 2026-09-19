// Secciones del vídeo — estilo de la plantilla Typst: tarjetas sand, chips,
// títulos Bungee, acentos gold/teal/red. Menos es más.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { Datos } from "./datos";
import {
  BROWN, GOLD, INK, ORANGE, PAPER, RED, SAND, SLATE, TEAL,
} from "./theme";

type Metrica = { valor: unknown; etiqueta: string };

export const Chip: React.FC<{ texto: string }> = ({ texto }) => (
  <div
    style={{
      fontFamily: "Bungee, sans-serif",
      fontSize: 26,
      color: PAPER,
      background: BROWN,
      padding: "10px 26px",
      borderRadius: 999,
      letterSpacing: 3,
      display: "inline-block",
    }}
  >
    {texto}
  </div>
);

const Card: React.FC<{
  titulo: string;
  cuerpo: React.ReactNode;
  pie?: string;
  acento?: string;
  delay?: number;
}> = ({ titulo, cuerpo, pie, acento = GOLD, delay = 0 }) => {
  const frame = useCurrentFrame();
  const op = interpolate(frame - delay, [0, 12], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const dy = interpolate(frame - delay, [0, 12], [26, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <div style={{
      opacity: op, transform: `translateY(${dy}px)`,
      background: SAND, borderLeft: `10px solid ${acento}`,
      borderRadius: 14, padding: "26px 34px",
      boxShadow: "0 6px 18px rgba(42,23,15,0.18)",
    }}>
      <div style={{ fontFamily: "Bungee", fontSize: 30, color: BROWN, marginBottom: 10 }}>
        {titulo}
      </div>
      <div style={{ fontSize: 27, color: INK, lineHeight: 1.35, fontFamily: "'DM Sans'" }}>
        {cuerpo}
      </div>
      {pie ? (
        <div style={{ marginTop: 12, fontSize: 22, color: TEAL, fontFamily: "'DM Sans'" }}>
          {pie}
        </div>
      ) : null}
    </div>
  );
};

const Etiqueta: React.FC<{ m: Metrica }> = ({ m }) => (
  <span style={{
    fontSize: 20, fontFamily: "'DM Sans'", fontStyle: "italic",
    color: m.etiqueta === "medido" ? TEAL : m.etiqueta === "estimado" ? ORANGE : SLATE,
    marginLeft: 12,
  }}>
    ({m.etiqueta})
  </span>
);

const Titulo: React.FC<{ texto: string }> = ({ texto }) => {
  const frame = useCurrentFrame();
  const op = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{
      fontFamily: "Bungee", fontSize: 54, color: INK,
      borderBottom: `6px solid ${GOLD}`, display: "inline-block",
      paddingBottom: 8, opacity: op,
    }}>
      {texto}
    </div>
  );
};

const Slide: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const fade = interpolate(frame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ background: PAPER, padding: "70px 110px", opacity: fade }}>
      {children}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 1 · portada

export const Portada: React.FC<{ datos: Datos }> = ({ datos }) => {
  const frame = useCurrentFrame();
  const op = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const crece = interpolate(frame, [5, 35], [0.85, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{
      background: PAPER, alignItems: "center", justifyContent: "center",
      flexDirection: "column", opacity: op,
    }}>
      <div style={{ transform: `scale(${crece})`, textAlign: "center" }}>
        <div style={{ fontFamily: "Bungee", fontSize: 130, color: INK }}>
          {datos.portada.titulo}
        </div>
        <div style={{
          fontFamily: "'DM Sans'", fontSize: 42, color: BROWN, marginTop: 18,
          fontStyle: "italic",
        }}>
          {datos.portada.subtitulo}
        </div>
        <div style={{ marginTop: 44, display: "flex", gap: 22, justifyContent: "center" }}>
          {datos.portada.chips.map((c, i) => (
            <div key={c} style={{
              opacity: interpolate(frame - 20 - i * 8, [0, 10], [0, 1], {
                extrapolateLeft: "clamp", extrapolateRight: "clamp",
              }),
            }}>
              <Chip texto={c} />
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 2 · problema

export const Problema: React.FC<{ datos: Datos }> = ({ datos }) => (
  <Slide>
    <Titulo texto="El problema" />
    <div style={{ display: "flex", gap: 30, marginTop: 50 }}>
      <Card titulo={`${datos.problema.n_facturas.valor} facturas`} acento={GOLD}
        cuerpo="PDFs nativos, escaneos, QRs, nombres no estándar — y trampas: proveedores fantasma, duplicados, instrucciones embebidas."
        delay={6} />
      <Card titulo={`${datos.problema.n_resultados.valor} resultados`} acento={TEAL}
        cuerpo={<>{datos.problema.resultados.join(" · ")}<br /><Etiqueta m={datos.problema.n_resultados} /></>}
        delay={16} />
      <Card titulo="La norma" acento={ORANGE}
        cuerpo={datos.problema.norma} delay={26} />
    </div>
    <div style={{ marginTop: 60, fontFamily: "'DM Sans'", fontSize: 30, color: BROWN, fontStyle: "italic" }}>
      “Ante duda razonable, escalar antes que pagar.”
    </div>
  </Slide>
);

// ---------------------------------------------------------------- 3 · escalera

const Rung: React.FC<{ nivel: string; titulo: string; dato: string; delay: number }> = ({
  nivel, titulo, dato, delay,
}) => {
  const frame = useCurrentFrame();
  const op = interpolate(frame - delay, [0, 12], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const dx = interpolate(frame - delay, [0, 12], [-40, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <div style={{
      opacity: op, transform: `translateX(${dx}px)`,
      display: "flex", alignItems: "center", gap: 24,
    }}>
      <div style={{
        fontFamily: "Bungee", fontSize: 30, color: PAPER, background: TEAL,
        borderRadius: 10, padding: "12px 18px", minWidth: 130, textAlign: "center",
      }}>
        {nivel}
      </div>
      <div style={{ fontFamily: "'DM Sans'", fontSize: 30, color: INK, flex: 1 }}>
        {titulo}
      </div>
      <div style={{ fontFamily: "Bungee", fontSize: 34, color: GOLD }}>{dato}</div>
    </div>
  );
};

export const Escalera: React.FC<{ datos: Datos }> = ({ datos }) => {
  const e = datos.escalera;
  const l1 = e.latencias.rung1 ?? { media: { valor: "—" }, p95: { valor: "—" } };
  const l2 = e.latencias.rung2 ?? { media: { valor: "—" }, p95: { valor: "—" } };
  return (
    <Slide>
      <Titulo texto="La escalera, por PÁGINA" />
      <div style={{ display: "flex", flexDirection: "column", gap: 26, marginTop: 46 }}>
        <Rung nivel="rung 1" titulo="capa de texto (pypdf) — usable" dato={`${e.texto_usable.valor} / 500`} delay={8} />
        <Rung nivel="rung 2" titulo="raster + QR (pypdfium2 + cv2)" dato={`${e.raster.valor} raster · ${e.solo_qr.valor} QR`} delay={20} />
        <Rung nivel="rung 3" titulo="tesseract (umbrales calibrados con el corpus)" dato="89.7 % pasa" delay={32} />
        <Rung nivel="rung 4" titulo={e.rung4} dato="1 en vuelo" delay={44} />
        <Rung nivel="rung 5" titulo={e.rung5} dato="escala" delay={56} />
      </div>
      <div style={{ display: "flex", gap: 60, marginTop: 50, fontFamily: "'DM Sans'", fontSize: 28, color: BROWN }}>
        <span>rung 1: {String(l1.media.valor)} media · p95 {String(l1.p95.valor)} <span style={{ color: TEAL }}>(medido)</span></span>
        <span>rung 2: {String(l2.media.valor)} media · p95 {String(l2.p95.valor)} <span style={{ color: TEAL }}>(medido)</span></span>
      </div>
    </Slide>
  );
};

// ---------------------------------------------------------------- 4 · decisiones

export const Decisiones: React.FC<{ datos: Datos }> = ({ datos }) => (
  <Slide>
    <Titulo texto="Decisiones (ADRs): qué y por qué" />
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 22, marginTop: 40 }}>
      {datos.decisiones.map((d, i) => (
        <Card key={d.titulo} titulo={d.titulo} cuerpo={d.porque}
          pie={d.evidencia} acento={i % 2 ? TEAL : GOLD} delay={8 + i * 10} />
      ))}
    </div>
  </Slide>
);

// ---------------------------------------------------------------- 5 · números

const Num: React.FC<{ grande: string; etiqueta: string; pie: string; acento: string; delay: number }> = ({
  grande, etiqueta, pie, acento, delay,
}) => {
  const frame = useCurrentFrame();
  const op = interpolate(frame - delay, [0, 12], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <div style={{
      opacity: op, background: SAND, borderRadius: 16, padding: "24px 30px",
      borderTop: `8px solid ${acento}`,
    }}>
      <div style={{ fontFamily: "Bungee", fontSize: 52, color: INK }}>{grande}</div>
      <div style={{ fontFamily: "'DM Sans'", fontSize: 24, color: BROWN, marginTop: 8 }}>
        {pie} <span style={{ fontStyle: "italic", color: TEAL }}>({etiqueta})</span>
      </div>
    </div>
  );
};

export const Numeros: React.FC<{ datos: Datos }> = ({ datos }) => {
  const n = datos.numeros;
  const fps = n.files_por_s_lote1 as Metrica;
  const r1 = n.rung1_files_per_s as Metrica;
  const coste = n.coste_cloud_eur as Metrica;
  const drills = n.drills as Metrica;
  const validador = n.validador as Metrica;
  const dist = n.distribucion_final as Metrica;
  return (
    <Slide>
      <Titulo texto="Números (medidos, no prometidos)" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, marginTop: 46 }}>
        <Num grande={`${fps.valor} files/s`} etiqueta="medido" pie="lote 1 completo (500)" acento={GOLD} delay={6} />
        <Num grande={`0.00 €`} etiqueta="estimado" pie="coste cloud lote 1" acento={TEAL} delay={14} />
        <Num grande={`${drills.valor}`} etiqueta="medido" pie="drills de resiliencia" acento={ORANGE} delay={22} />
        <Num grande={`${validador.valor}`} etiqueta="medido" pie="validador de contrato" acento={GOLD} delay={30} />
        <Num grande={String(dist.valor).split(" · ")[0]} etiqueta="medido" pie={String(dist.valor)} acento={TEAL} delay={38} />
        <Num grande="13 pág." etiqueta="medido" pie="albertitos_plan.pdf desde el store" acento={ORANGE} delay={46} />
      </div>
      <div style={{ marginTop: 34, fontFamily: "'DM Sans'", fontSize: 26, color: SLATE }}>
        fuentes: .sdd/metrics/ — cada cifra lleva su etiqueta (medido / estimado)
      </div>
    </Slide>
  );
};

// ---------------------------------------------------------------- 6 · traza

export const Traza: React.FC<{ datos: Datos }> = ({ datos }) => {
  const t = datos.traza;
  if (!t.disponible) {
    return (<Slide><Titulo texto="Trazabilidad" /></Slide>);
  }
  const pasos: [string, string][] = [
    ["PDF", `${t.file_id ?? ""} (sha256 ${String(t.sha256).slice(0, 8)}…)`],
    ["rungs", (t.rungs ?? []).join(" → ") || "—"],
    ["campos", (t.campos_parseados ?? []).join(", ")],
    ["reglas", (t.reglas ?? []).slice(0, 6).join(" · ") + " …"],
    ["decisión", `${t.resultado ?? ""} (determinista, con snapshot de config)`],
  ];
  return (
    <Slide>
      <Titulo texto="Un ejemplo real, de punta a punta" />
      <div style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 44 }}>
        {pasos.map(([paso, detalle], i) => (
          <Card key={paso} titulo={paso} acento={[GOLD, TEAL, ORANGE, SLATE, RED][i]}
            cuerpo={detalle} delay={6 + i * 12} />
        ))}
      </div>
      <div style={{ marginTop: 30, fontFamily: "'DM Sans'", fontSize: 25, color: SLATE }}>
        ledger SQLite + JSONL append-only · cache (sha256, rung, versión, config) · idempotente
      </div>
    </Slide>
  );
};

// ---------------------------------------------------------------- 7 · cierre

export const Cierre: React.FC<{ datos: Datos }> = ({ datos }) => (
  <Slide>
    <Titulo texto="La entrega" />
    <div style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 44 }}>
      {datos.cierre.entregables.map((e, i) => (
        <Card key={e} titulo={`· ${e}`} acento={i === 0 ? GOLD : i === 1 ? TEAL : ORANGE}
          cuerpo="" delay={6 + i * 12} />
      ))}
      <div style={{ marginTop: 26, fontFamily: "'DM Sans'", fontSize: 30, color: BROWN }}>
        Bonus: {datos.cierre.bonus}
      </div>
      <div style={{ marginTop: 18, fontFamily: "Bungee", fontSize: 40, color: RED }}>
        gracias, Alberto.
      </div>
    </div>
  </Slide>
);
