/**
 * ClientServer — bloque autónomo que explica el reparto CLIENTE / SERVIDOR.
 *
 * Contrato congelado (otro componente lo importa así):
 *   import { ClientServer } from './ClientServer';
 *   <ClientServer f={frameLocalDelBeat} />
 *
 * `f` = frame local al inicio del beat; el bloque anima su propia entrada con
 * fades/rise cortos (14-20 frames, Easing.out(cubic)), el mismo patrón que el
 * resto del vídeo. No usa `useCurrentFrame` ni `useVideoConfig`: es puro
 * respecto a `f`, así que se puede montar dentro de una `Sequence` o de una
 * escena ya recortada.
 *
 * Caja exterior: 1500 × 440 px (no depende del padre más allá de que lo
 * centren dentro del área de contenido de 1740 px).
 *
 * Copia real (fuentes citadas en el informe del ticket):
 * - `src/filemaid/desktop/watcher.py` — vigilancia de una carpeta elegida.
 * - `docs/capacidad_y_coste.md` — escalera de extracción de 7 escalones.
 * - `src/filemaid/rules/engine.py` + `docs/db-mig.md` — el resultado lo emite
 *   solo el motor puro (determinista).
 * - `docs/db-mig.md` — PouchDB local (LevelDB) decide en standalone;
 *   `PouchDB.sync(remote_url)` con CouchDB remoto, best-effort, lote de 16;
 *   cola de revisión (facturas retenidas) y overrides como retroalimentación.
 */
import React from 'react';
import { Easing, interpolate } from 'remotion';
import { C } from './scenes';

const DISPLAY = 'Bungee, system-ui, sans-serif';
const BODY = 'DM Sans, system-ui, sans-serif';
const MONO = "'DejaVu Sans Mono', 'Courier New', monospace";

/** Caja exterior del bloque (px). */
export const CS_WIDTH = 1500;
export const CS_HEIGHT = 440;

// Entrada estándar del vídeo: opacidad + subida leve en 18 frames.
const enter = (f: number, delay: number, dist = 26): React.CSSProperties => {
  const p = interpolate(f, [delay, delay + 18], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  return { opacity: p, transform: `translateY(${(1 - p) * dist}px)` };
};

// Sin servidor la app sigue decidiendo: el store local es la única persistencia
// runtime (docs/db-mig.md, «Motor y seam»).
const CLIENTE = [
  'Vigila la carpeta · watcher',
  'Escalera de extracción',
  'Motor de reglas determinista',
  'Store local: decide por sí sola',
];

// Remoto = réplica CouchDB + cola de revisión + histórico de correcciones.
const SERVIDOR = [
  'Replicación nativa con CouchDB',
  'Sube decisiones y evidencia',
  'Cola de revisión: retenidas',
  'Histórico · corpus de overrides',
];

const Panel: React.FC<{
  f: number;
  title: string;
  subtitle: string;
  accent: string;
  bullets: string[];
  start: number;
}> = ({ f, title, subtitle, accent, bullets, start }) => (
  <div style={{
    ...enter(f, start, 30),
    flex: 1,
    minWidth: 0,
    background: C.panel,
    border: `2px solid ${C.ink}`,
    padding: '24px 26px',
    display: 'flex',
    flexDirection: 'column',
  }}>
    <div style={{ borderBottom: `2px solid ${accent}`, paddingBottom: 12, marginBottom: 16 }}>
      <div style={{ fontFamily: DISPLAY, fontSize: 44, lineHeight: 1.05, color: C.ink }}>{title}</div>
      <div style={{ fontFamily: DISPLAY, fontSize: 34, lineHeight: 1.2, color: accent, letterSpacing: 0.5 }}>
        {subtitle}
      </div>
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {bullets.map((b, i) => (
        <div
          key={b}
          style={{ ...enter(f, start + 14 * (i + 1), 18), display: 'flex', alignItems: 'flex-start', gap: 12 }}
        >
          <div style={{ width: 12, height: 12, marginTop: 9, flex: '0 0 auto', background: accent }} />
          <div style={{ fontSize: 26, lineHeight: 1.3, color: C.ink }}>{b}</div>
        </div>
      ))}
    </div>
  </div>
);

const Flecha: React.FC<{ f: number; delay: number; hacia: 'der' | 'izq'; color: string }> = ({
  f, delay, hacia, color,
}) => (
  <svg width={280} height={40} viewBox="0 0 280 40" style={enter(f, delay, 0)}>
    {hacia === 'der' ? (
      <>
        <line x1={8} y1={20} x2={250} y2={20} stroke={color} strokeWidth={5} />
        <polygon points="280,20 246,4 246,36" fill={color} />
      </>
    ) : (
      <>
        <line x1={30} y1={20} x2={272} y2={20} stroke={color} strokeWidth={5} />
        <polygon points="0,20 34,4 34,36" fill={color} />
      </>
    )}
  </svg>
);

// Indicador bidireccional: lo que sube (evidencia/decisiones) y lo que baja
// (overrides), en segundo plano y solo cuando hay red.
const Sync: React.FC<{ f: number }> = ({ f }) => (
  <div style={{
    width: 300,
    flex: '0 0 auto',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  }}>
    <div style={{
      ...enter(f, 58),
      fontFamily: BODY, fontWeight: 700, fontSize: 24, letterSpacing: 0.6,
      lineHeight: 1.25, color: C.ink, textAlign: 'center',
    }}>
      sync en segundo plano
    </div>
    <Flecha f={f} delay={66} hacia="der" color={C.ink} />
    <Flecha f={f} delay={76} hacia="izq" color={C.teal} />
    <div style={{
      ...enter(f, 84),
      fontSize: 24, lineHeight: 1.25, color: C.brown, textAlign: 'center',
    }}>
      solo cuando hay red
    </div>
    <div style={{
      ...enter(f, 90),
      fontFamily: MONO, fontSize: 24, lineHeight: 1.25, color: C.teal, textAlign: 'center',
    }}>
      PouchDB ↔ CouchDB
    </div>
  </div>
);

// Regla de independencia.
const Regla: React.FC<{ f: number }> = ({ f }) => (
  <div style={{
    ...enter(f, 98),
    height: 66,
    flex: '0 0 auto',
    background: C.okBg,
    border: `2px solid ${C.ink}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 20,
  }}>
    <div style={{ width: 16, height: 16, flex: '0 0 auto', background: C.ink }} />
    <div style={{ fontFamily: DISPLAY, fontSize: 30, lineHeight: 1.1, color: C.ink }}>
      Sin servidor sigue decidiendo · sincroniza al volver
    </div>
  </div>
);

export const ClientServer: React.FC<{ f: number }> = ({ f }) => (
  <div style={{
    width: CS_WIDTH,
    height: CS_HEIGHT,
    display: 'flex',
    flexDirection: 'column',
    gap: 18,
    fontFamily: BODY,
    color: C.ink,
  }}>
    <div style={{ display: 'flex', gap: 18, flex: 1, minHeight: 0, alignItems: 'stretch' }}>
      <Panel
        f={f} start={0}
        title="CLIENTE" subtitle="APP DE ESCRITORIO"
        accent={C.ink} bullets={CLIENTE}
      />
      <Sync f={f} />
      <Panel
        f={f} start={8}
        title="SERVIDOR" subtitle="COUCHDB REMOTO"
        accent={C.teal} bullets={SERVIDOR}
      />
    </div>
    <Regla f={f} />
  </div>
);
