import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  spring,
  Easing,
} from 'remotion';
import {
  C,
  METRICS,
  ESCALERA,
  DRILLS,
  REGLAS,
  CASO_DUPLICADO,
  CASO_SCAN,
  CASO_ESCALAR,
  SCENES,
} from './scenes';
import shotDashboard from '../assets/shot-dashboard.png';
import shotRevision from '../assets/shot-revision.png';
import shotLogs from '../assets/shot-logs.png';

const DISPLAY = 'Bungee, system-ui, sans-serif';
const BODY = 'DM Sans, system-ui, sans-serif';
const MONO = "'DejaVu Sans Mono', 'Courier New', monospace";

const Frame: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: C.paper, color: C.ink, fontFamily: BODY, padding: '60px 90px' }}>
    {children}
  </AbsoluteFill>
);

const fade = (frame: number, delay: number, dur = 18) =>
  interpolate(frame, [delay, delay + dur], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

const rise = (frame: number, delay: number, dist = 40) => {
  const p = interpolate(frame, [delay, delay + 20], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic),
  });
  return { opacity: p, transform: `translateY(${(1 - p) * dist}px)` };
};

const Chip: React.FC<{ label: string; color: string; bg: string }> = ({ label, color, bg }) => (
  <span style={{
    fontFamily: DISPLAY, fontSize: 30, color, background: bg,
    border: `2px solid ${color}`, padding: '10px 26px', marginRight: 24,
  }}>{label}</span>
);

const SectionKicker: React.FC<{ n: string; title: string }> = ({ n, title }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ ...rise(f, 0), marginBottom: 40 }}>
      <div style={{ fontFamily: BODY, fontSize: 26, color: C.teal, fontWeight: 700, letterSpacing: 2 }}>
        {n}
      </div>
      <div style={{ fontFamily: DISPLAY, fontSize: 66, lineHeight: 1.1 }}>{title}</div>
      <div style={{ width: 140, height: 8, background: C.gold, marginTop: 16 }} />
    </div>
  );
};

const Escena: React.FC<{ idx: number; children: React.ReactNode }> = ({ idx, children }) => {
  const { durationInFrames } = useVideoConfig();
  const start = SCENES.slice(0, idx).reduce((a, s) => a + s.frames, 0);
  const len = SCENES[idx].frames;
  const f = useCurrentFrame() - start;
  const inP = interpolate(f, [0, 14], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const outP = interpolate(f, [len - 12, len], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  if (f < 0 || f >= len) return null;
  return <div style={{ opacity: inP * outP }}>{children}</div>;
};

// ── 1 · Portada ──────────────────────────────────────────────────────────────
const Portada: React.FC = () => {
  const f = useCurrentFrame();
  const scale = spring({ frame: f, fps: 30, config: { damping: 14, mass: 0.7 } });
  return (
    <Escena idx={0}>
      <Frame>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 190, transform: `scale(${scale})`, letterSpacing: 4 }}>
            FILEMAID
          </div>
          <div style={{ width: 420, height: 10, background: C.gold, margin: '28px 0' }} />
          <div style={{ fontSize: 52, color: C.brown, opacity: fade(f, 25) }}>
            De 500 facturas a una decisión
          </div>
          <div style={{ marginTop: 70, opacity: fade(f, 55) }}>
            <Chip label="FACTURA" color={C.brown} bg={C.panel} />
            <Chip label="DECISIÓN" color={C.orange} bg={C.warnBg} />
            <Chip label="TRAZA" color={C.teal} bg={C.okBg} />
          </div>
          <div style={{ marginTop: 80, fontFamily: MONO, fontSize: 26, color: C.brown, opacity: fade(f, 85) }}>
            Maisa · HackSpain 2026 · 500 Sombras de Alberto
          </div>
        </div>
      </Frame>
    </Escena>
  );
};

// ── 2 · Problema ─────────────────────────────────────────────────────────────
const Problema: React.FC = () => {
  const f = useCurrentFrame();
  const cards = [
    { big: '500', label: 'facturas PDF', sub: 'nativas y escaneadas', color: C.ink },
    { big: '1', label: 'Excel maestro', sub: 'proveedores · pedidos · normas', color: C.ink },
    { big: 'ERP 2009', label: 'legado', sub: 'estado de pedidos, lento', color: C.ink },
  ];
  return (
    <Escena idx={1}>
      <Frame>
        <SectionKicker n="EL PROBLEMA" title="El mundo de Alberto" />
        <div style={{ display: 'flex', gap: 30 }}>
          {cards.map((c, i) => (
            <div key={c.label} style={{
              ...rise(f, 20 + i * 14), flex: 1, background: C.panel, border: `2px solid ${C.ink}`,
              padding: '36px 30px',
            }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 76, color: c.color }}>{c.big}</div>
              <div style={{ fontSize: 34, fontWeight: 700, marginTop: 8 }}>{c.label}</div>
              <div style={{ fontSize: 26, color: C.brown, marginTop: 6 }}>{c.sub}</div>
            </div>
          ))}
        </div>
        <div style={{ ...rise(f, 90), marginTop: 60, fontSize: 40 }}>
          Para cada factura hay que decidir, sin inventar:
        </div>
        <div style={{ ...rise(f, 110), marginTop: 26 }}>
          <Chip label="PAGAR" color={C.teal} bg={C.okBg} />
          <Chip label="NO_PAGAR" color={C.red} bg={C.badBg} />
          <Chip label="ESCALAR" color={C.orange} bg={C.warnBg} />
        </div>
        <div style={{ ...rise(f, 150), marginTop: 56, fontSize: 34, fontStyle: 'italic', color: C.brown }}>
          «Ante duda razonable, escalar antes que pagar.»
        </div>
      </Frame>
    </Escena>
  );
};

// ── 3 · Producto ─────────────────────────────────────────────────────────────
const CAPTURAS = [
  { src: shotDashboard, alt: 'Dashboard: contadores por resultado' },
  { src: shotRevision, alt: 'Revisión: candidatos y reglas lado a lado' },
  { src: shotLogs, alt: 'Trazas: eventos por factura' },
];

const Producto: React.FC = () => {
  const f = useCurrentFrame();
  // Rotación de capturas: ~6,5 s cada una dentro de los 600 frames de la escena.
  const idx = Math.min(Math.floor(f / 200), CAPTURAS.length - 1);
  const cap = CAPTURAS[idx];
  const capIn = fade(f - idx * 200, 0, 14);
  const pasos = [
    { icon: '📁', t: 'Watcher de carpeta', s: 'suelta PDFs → se ingesta sola' },
    { icon: '🌙', t: 'Lote 24/7', s: 'sin prompts: nadie duerme con el proceso' },
    { icon: '🔔', t: 'Notificación nativa', s: 'Qt al escritorio solo al ESCALAR' },
    { icon: '🧾', t: 'Revisión humana', s: 'candidatos lado a lado, override con procedencia' },
    { icon: '🔁', t: 'Sync CouchDB', s: 'replicación nativa, facturas disputadas retenidas' },
  ];
  return (
    <Escena idx={2}>
      <Frame>
        <SectionKicker n="EL PRODUCTO" title="Una app de escritorio, no un script" />
        <div style={{ display: 'flex', gap: 30 }}>
          <div style={{ flex: 1 }}>
            {pasos.map((p, i) => (
              <div key={p.t} style={{
                ...rise(f, 20 + i * 16), display: 'flex', alignItems: 'center', gap: 18,
                background: C.panel, border: `2px solid ${C.ink}`, padding: '12px 20px',
                marginBottom: 12,
              }}>
                <div style={{ fontSize: 36 }}>{p.icon}</div>
                <div style={{ fontFamily: DISPLAY, fontSize: 27, width: 400 }}>{p.t}</div>
                <div style={{ fontSize: 24, color: C.brown }}>{p.s}</div>
              </div>
            ))}
          </div>
          <div style={{ width: 620, ...rise(f, 60) }}>
            <div style={{ border: `3px solid ${C.ink}`, background: '#fff', padding: 10 }}>
              <img src={cap.src} alt={cap.alt} style={{ width: '100%', display: 'block', opacity: capIn }} />
            </div>
            <div style={{ marginTop: 10, fontSize: 22, fontFamily: MONO, color: C.brown, textAlign: 'center' }}>
              {cap.alt}
            </div>
          </div>
        </div>
        <div style={{ ...rise(f, 110), marginTop: 22, fontSize: 28, color: C.brown }}>
          Misma UI Vue en navegador y ventana nativa (pywebview) · estética documental Typst
        </div>
      </Frame>
    </Escena>
  );
};

// ── 4 · Escalera ─────────────────────────────────────────────────────────────
const Escalera: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <Escena idx={3}>
      <Frame>
        <SectionKicker n="ARQUITECTURA · EXTRACCIÓN" title="La escalera de confianza" />
        <div style={{ display: 'flex', gap: 40 }}>
          <div style={{ flex: 1.35 }}>
            {ESCALERA.map((e, i) => (
              <div key={e.n} style={{
                ...rise(f, 15 + i * 11), display: 'grid', gridTemplateColumns: '60px 1fr 220px',
                gap: 16, alignItems: 'center', background: i < 4 ? C.okBg : C.panel,
                border: `2px solid ${C.ink}`, padding: '10px 18px', marginBottom: 8,
              }}>
                <div style={{
                  fontFamily: DISPLAY, fontSize: 26, background: C.ink, color: C.paper,
                  width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{e.n}</div>
                <div>
                  <div style={{ fontWeight: 800, fontSize: 28 }}>{e.tech}</div>
                  <div style={{ fontSize: 22, color: C.brown }}>{e.sub}</div>
                </div>
                <div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 22 }}>
                  <div style={{ color: C.teal }}>{e.speed}</div>
                  <div style={{ color: C.orange }}>{e.cost}</div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ ...rise(f, 100), border: `2px solid ${C.ink}`, background: C.panel, padding: 28 }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 30, marginBottom: 18 }}>Medido · 500 PDFs reales</div>
              {[
                ['Escalón 1 (texto) resuelve', `${METRICS.textoUsablePct} %`],
                ['Velocidad escalón 1', `${METRICS.rung1FilesPerS} archivos/s`],
                ['Caen a raster/QR', `${METRICS.raster} archivos`],
                ['Coste escalones 1–4', '0,00 €'],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 27, padding: '8px 0', borderTop: `1px solid ${C.borderSoft}` }}>
                  <span style={{ color: C.brown }}>{k}</span>
                  <span style={{ fontFamily: MONO, fontWeight: 700 }}>{v}</span>
                </div>
              ))}
            </div>
            <div style={{ ...rise(f, 130), marginTop: 22, fontSize: 26, color: C.brown, fontStyle: 'italic' }}>
              Cada escalón degrada al siguiente; ninguno bloquea el lote.
            </div>
          </div>
        </div>
      </Frame>
    </Escena>
  );
};

// ── 5 · Trazabilidad ─────────────────────────────────────────────────────────
const VerdictBadge: React.FC<{ result: string; size?: number }> = ({ result, size = 40 }) => {
  const color = result === 'PAGAR' ? C.teal : result === 'NO_PAGAR' ? C.red : C.orange;
  const bg = result === 'PAGAR' ? C.okBg : result === 'NO_PAGAR' ? C.badBg : C.warnBg;
  return (
    <span style={{ fontFamily: DISPLAY, fontSize: size, color, background: bg, border: `3px solid ${color}`, padding: '8px 28px' }}>
      {result}
    </span>
  );
};

const Regla: React.FC<{ code: string; state: 'PASS' | 'FAIL' | 'UNKNOWN' }> = ({ code, state }) => {
  const color = state === 'PASS' ? C.teal : state === 'FAIL' ? C.red : C.orange;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 25, padding: '7px 14px', borderBottom: `1px solid ${C.borderSoft}` }}>
      <span>{code}</span>
      <span style={{ color, fontWeight: 800 }}>{state}</span>
    </div>
  );
};

const Traza: React.FC = () => {
  const f = useCurrentFrame();
  const reglasDup = REGLAS.map((code) => ({ code, state: CASO_DUPLICADO.fails.includes(`${code}:FAIL` as never) ? 'FAIL' as const : 'PASS' as const }));
  const reglasScan = REGLAS.map((code) => ({ code, state: CASO_SCAN.unknowns === 11 && code !== 'NO_DOUBLE_PAYMENT' && code !== 'NO_EMBEDDED_INSTRUCTIONS' && code !== 'PROVEEDOR_FANTASMA' ? 'UNKNOWN' as const : 'PASS' as const }));
  return (
    <Escena idx={4}>
      <Frame>
        <SectionKicker n="TRAZABILIDAD" title="Sigamos una decisión real" />
        <div style={{ display: 'flex', gap: 36 }}>
          <div style={{ flex: 1, ...rise(f, 20) }}>
            <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700 }}>{CASO_DUPLICADO.file_id}</div>
            <div style={{ margin: '14px 0 10px' }}><VerdictBadge result={CASO_DUPLICADO.result} /></div>
            <div style={{ border: `2px solid ${C.ink}`, background: C.panel }}>
              {reglasDup.map((r) => <Regla key={r.code} code={r.code} state={r.state} />)}
            </div>
            <div style={{ marginTop: 12, fontSize: 24, color: C.brown }}>{CASO_DUPLICADO.nota}</div>
          </div>
          <div style={{ flex: 1, ...rise(f, 60) }}>
            <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700 }}>{CASO_SCAN.file_id}</div>
            <div style={{ margin: '14px 0 10px' }}><VerdictBadge result={CASO_SCAN.result} /></div>
            <div style={{ border: `2px solid ${C.ink}`, background: C.panel }}>
              {reglasScan.map((r) => <Regla key={r.code} code={r.code} state={r.state} />)}
            </div>
            <div style={{ marginTop: 12, fontSize: 24, color: C.brown }}>{CASO_SCAN.nota}</div>
          </div>
        </div>
        <div style={{ ...rise(f, 110), marginTop: 34, display: 'flex', gap: 18 }}>
          {['sha256', 'extractor+versión', 'confianza por candidato', 'config_version', 'latencia_ms'].map((e) => (
            <span key={e} style={{ fontFamily: MONO, fontSize: 23, background: C.sand, border: `1px solid ${C.ink}`, padding: '8px 18px' }}>{e}</span>
          ))}
        </div>
      </Frame>
    </Escena>
  );
};

// ── 6 · ADRs ─────────────────────────────────────────────────────────────────
const Adrs: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <Escena idx={5}>
      <Frame>
        <SectionKicker n="ARQUITECTURA · DECISIONES" title="Motor puro + 8 ADRs" />
        <div style={{ ...rise(f, 15), border: `2px solid ${C.ink}`, background: C.okBg, padding: '20px 28px', marginBottom: 24 }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 34 }}>ADR-06 · Provenance de candidatos</div>
          <div style={{ fontSize: 28, marginTop: 8 }}>
            El motor evaluaba el PRIMER candidato «total» (el subtotal): <b>87 de 108 NO_PAGAR eran falsos</b>.
            Ahora evalúa todos los candidatos y cita el elegido: <b>86 corregidos a PAGAR, 0 regresiones</b>.
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {[
            ['ADR · Motor determinista', 'mismos campos + misma config ⇒ misma salida, byte a byte; snapshot de umbrales en cada decisión'],
            ['ADR-08 · Política como datos', 'FAIL→NO_PAGAR o ESCALAR por regla en rules.yaml; PAGAR por FAIL prohibido por el motor'],
            ['ADR · PouchDB + CouchDB', 'replicación nativa; disputas retenidas, fail-closed'],
            ['ADR · pywebview, no Electron', 'misma UI Vue en Linux/Win/Mac sin 200 MB de runtime'],
          ].map(([t, s], i) => (
            <div key={t} style={{ ...rise(f, 50 + i * 15), border: `2px solid ${C.ink}`, background: C.panel, padding: '16px 24px' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 27 }}>{t}</div>
              <div style={{ fontSize: 24, color: C.brown, marginTop: 6 }}>{s}</div>
            </div>
          ))}
        </div>
      </Frame>
    </Escena>
  );
};

// ── 7 · Resiliencia ──────────────────────────────────────────────────────────
const Resiliencia: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <Escena idx={6}>
      <Frame>
        <SectionKicker n="RESILIENCIA" title="Caerse no es opción: degradar" />
        {DRILLS.map((d, i) => (
          <div key={d.name} style={{
            ...rise(f, 20 + i * 18), display: 'flex', alignItems: 'center', gap: 24,
            border: `2px solid ${C.ink}`, background: C.panel, padding: '16px 26px', marginBottom: 16, width: 1400,
          }}>
            <span style={{ fontFamily: DISPLAY, fontSize: 30, color: C.teal }}>PASS</span>
            <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700, width: 480 }}>{d.name}</span>
            <span style={{ fontSize: 27, color: C.brown }}>{d.detail}</span>
          </div>
        ))}
        <div style={{ ...rise(f, 110), marginTop: 28, fontSize: 29 }}>
          Idempotencia por <span style={{ fontFamily: MONO }}>(sha256, stage, engine_version, config_version)</span> —
          reanudar nunca duplica ni re-factura.
        </div>
      </Frame>
    </Escena>
  );
};

// ── 8 · Escala y coste ───────────────────────────────────────────────────────
const Escala: React.FC = () => {
  const f = useCurrentFrame();
  const filas: [string, string, string][] = [
    ['Corrida real · lote 1 (500 PDFs)', `${METRICS.latenciaTotalS} s  ≈  ${METRICS.filesPerS} archivos/s`, 'medido'],
    ['Coste cloud del lote', `${METRICS.costeCloudEur.toFixed(2)} €  (0 lecturas facturables)`, 'medido'],
    ['VLM local (escalón 4)', `~${Math.round(METRICS.vlmLocalMeanMs / 1000)} s/página · 0 €`, 'medido'],
    ['Cloud VLM (escalón 7)', `~${Math.round(METRICS.vlmCloudMeanMs / 1000)} s/lectura · solo páginas difíciles`, 'medido'],
    ['10 000 facturas', '~40 min en un portátil · 0 € en escalones 1–4', 'estimación'],
  ];
  return (
    <Escena idx={7}>
      <Frame>
        <SectionKicker n="ESCALA · COSTE · LÍMITES" title="La fórmula, con números" />
        <div style={{ border: `2px solid ${C.ink}`, background: C.panel, width: 1500 }}>
          {filas.map(([k, v, tag], i) => (
            <div key={k} style={{ ...rise(f, 15 + i * 14), display: 'grid', gridTemplateColumns: '560px 1fr 150px', alignItems: 'center', padding: '16px 26px', borderBottom: i < filas.length - 1 ? `1px solid ${C.borderSoft}` : 'none' }}>
              <span style={{ fontSize: 28 }}>{k}</span>
              <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700 }}>{v}</span>
              <span style={{ fontSize: 22, color: tag === 'medido' ? C.teal : C.orange, fontFamily: MONO }}>{tag}</span>
            </div>
          ))}
        </div>
        <div style={{ ...rise(f, 110), marginTop: 34, fontSize: 30, color: C.brown }}>
          Más volumen: concurrencia por bloques · nuevo tipo de archivo: un extractor + umbrales, cero cambios en reglas.
        </div>
      </Frame>
    </Escena>
  );
};

export const FilemaidVideo: React.FC = () => {
  const f = useCurrentFrame();
  void f;
  return (
    <>
      <Portada />
      <Problema />
      <Producto />
      <Escalera />
      <Traza />
      <Adrs />
      <Resiliencia />
      <Escala />
    </>
  );
};
