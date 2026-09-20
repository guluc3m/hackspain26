import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
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
import { useFonts } from './fonts';
import { ClientServer } from './ClientServer';
import shotDashboard from '../assets/shot-dashboard.png';
import shotRevision from '../assets/shot-revision.png';
import shotLogs from '../assets/shot-logs.png';

const DISPLAY = 'Bungee, system-ui, sans-serif';
const BODY = 'DM Sans, system-ui, sans-serif';
const MONO = "'DejaVu Sans Mono', 'Courier New', monospace";

// ── Contrato de audio (video/narracion/SPEC.md) ─────────────────────────────
// Voz TTS ya grabada: un wav por escena; `VOZ` = frame LOCAL (dentro de la
// escena) en el que entra la voz. La música cubre los 5400 frames a 0.12.
const VOZ = [30, 30, 36, 60, 75, 45, 30, 30];

// Reparto local de tiempos P→S→B/C por escena: [inicio de SOLUCIÓN, inicio de
// BENEFICIO/CAVEAT]. Derivado de las TOMAS NUEVAS (frases y duración medida de
// video/narracion/guion_tts.md): cada frontera cae en la frase donde la voz
// entra en ese tiempo, y el arranque del B/C se coloca para que el último
// cambio visual de la escena caiga dentro de los ~2 s finales (sin cola
// congelada después de la voz).
const TIEMPOS: [number, number][] = [
  [ 95, 240],  // 1 portada: «500 facturas» → «esto es filemaid… las lee, las comprueba» → «enseñando siempre la prueba»
  [145, 350],  // 2 problema: «decidir parece fácil» → «los LLM tardan / el OCR se tropieza» → «ante la duda… escalar antes que pagar»
  [125, 440],  // 3 producto: «el producto es la app de escritorio» → «vigila la carpeta… el servidor no decide» → «y si algo huele raro, un humano revisa»
  [105, 640],  // 4 escalera: «¿cómo lee cada página?» → los 7 escalones → «y solo al final la nube» + «cada escalón degrada con calma»
  [140, 600],  // 5 traza: «¿por qué no se paga esta?» → los 3 casos reales → «cada decisión guarda su evidencia» (cierre: «todo se puede auditar»)
  [135, 334],  // 6 adrs: «una IA que decide distinto no es pagable» → «el motor del cliente es puro» → «cuando encontramos un fallo… ocho ADRs»
  [110, 220],  // 7 resiliencia: «¿y si un proveedor cae?» → los 4 drills → «se reanuda sin duplicados» + «si el servidor cae…» + «degradar»
  [ 55, 240],  // 8 escala: «¿y el coste?» → «la fórmula es simple: el 94 % cuesta cero» → «quinientas facturas en dos minutos…»
];

const sceneStart = (idx: number) => SCENES.slice(0, idx).reduce((a, s) => a + s.frames, 0);
const useFrameLocal = (idx: number) => useCurrentFrame() - sceneStart(idx);

const Frame: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: C.paper, color: C.ink, fontFamily: BODY, padding: '60px 90px', display: 'flex', flexDirection: 'column' }}>
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

// Opacidad de un tiempo narrativo: entra en `a`, sale al empezar el siguiente.
const ventana = (f: number, a: number, b: number) =>
  interpolate(f, [a, a + 14, b - 14, b], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

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
  void durationInFrames;
  const start = sceneStart(idx);
  const len = SCENES[idx].frames;
  const f = useCurrentFrame() - start;
  const inP = interpolate(f, [0, 14], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const outP = interpolate(f, [len - 12, len], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  if (f < 0 || f >= len) return null;
  return <div style={{ opacity: inP * outP }}>{children}</div>;
};

// Voz narrada de la escena: wav de Worker B. Todas las escenas están montadas
// desde el frame 0 (solo se ocultan visualmente), así que el `from` de la
// Sequence debe ser el inicio GLOBAL de la escena + el delay del spec.
const Voz: React.FC<{ idx: number }> = ({ idx }) => (
  <Sequence from={sceneStart(idx) + VOZ[idx]}>
    <Audio src={staticFile(`narracion/esc${idx + 1}.wav`)} volume={1} />
  </Sequence>
);

// Área de contenido bajo el kicker: los 3 tiempos narrativos se apilan y se
// relevan (solo uno visible por frame) sincronizados con la voz.
const Tiempos: React.FC<{
  f: number; tS: number; tB: number; len: number;
  p: React.ReactNode; s: React.ReactNode; b: React.ReactNode;
}> = ({ f, tS, tB, len, p, s, b }) => (
  <div style={{ position: 'relative', flex: 1 }}>
    <div style={{ position: 'absolute', inset: 0, opacity: ventana(f, 0, tS) }}>{p}</div>
    <div style={{ position: 'absolute', inset: 0, opacity: ventana(f, tS, tB) }}>{s}</div>
    <div style={{ position: 'absolute', inset: 0, opacity: ventana(f, tB, len) }}>{b}</div>
  </div>
);

// Tarjeta tachada: alternativa ingenua descartada con línea animada (sin emoji).
const Tachada: React.FC<{ titulo: string; motivo: string; f: number; delay: number }> = ({ titulo, motivo, f, delay }) => {
  const p = interpolate(f, [delay, delay + 16], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic),
  });
  return (
    <div style={{
      position: 'relative', ...rise(f, delay - 22), flex: 1,
      background: C.panel, border: `2px solid ${C.ink}`, padding: '40px 40px',
    }}>
      <div style={{ fontFamily: DISPLAY, fontSize: 48 }}>{titulo}</div>
      <div style={{ fontSize: 34, color: C.brown, marginTop: 12 }}>{motivo}</div>
      <div style={{
        position: 'absolute', left: '4%', width: '92%', top: '56%', height: 8,
        background: C.red, transform: `scaleX(${p})`, transformOrigin: 'left center',
      }} />
    </div>
  );
};

// ── 1 · Portada ──────────────────────────────────────────────────────────────
// P: «500 facturas al mes» · S: filemaid lee, comprueba y decide · B: siempre enseña la prueba.
const Portada: React.FC = () => {
  const f = useFrameLocal(0);
  const num = spring({ frame: f, fps: 30, config: { damping: 14, mass: 0.6 } });
  // Slots verticales FIJOS: cada elemento ocupa una posición propia y aparece
  // en sitio (fade/rise), sin insertar filas en el flujo — así nada se desplaza
  // mientras el siguiente hace su entrada (sin offset en los cruces).
  const slot = (top: number): React.CSSProperties => ({
    position: 'absolute', left: 0, right: 0, top, textAlign: 'center',
  });
  return (
    <Escena idx={0}>
      <Frame>
        <Voz idx={0} />
        <div style={{ position: 'relative', height: '100%' }}>
          <div style={{ ...slot(20) }}>
            <div style={{ fontFamily: DISPLAY, fontSize: 240, lineHeight: 1, transform: `scale(${num})` }}>
              {METRICS.nArchivos}
            </div>
            <div style={{ fontSize: 44, color: C.brown, marginTop: 16, opacity: fade(f, 36) }}>
              facturas al mes, en PDF
            </div>
          </div>
          <div style={{ position: 'absolute', top: 370, left: '50%', width: 420, height: 10, marginLeft: -210, background: C.gold, opacity: fade(f, 60) }} />
          <div style={{ ...slot(440), fontFamily: DISPLAY, fontSize: 130, letterSpacing: 4, opacity: fade(f, 95) }}>
            FILEMAID
          </div>
          <div style={{ ...slot(608), fontSize: 40, color: C.brown, opacity: fade(f, 120) }}>
            las lee · las comprueba · decide
          </div>
          <div style={{ ...slot(690), ...rise(f, 240), fontSize: 46, fontStyle: 'italic' }}>
            «y siempre enseña la prueba»
          </div>
          <div style={{ ...slot(780), display: 'flex', justifyContent: 'center', opacity: fade(f, 265) }}>
            <Chip label="FACTURA" color={C.brown} bg={C.panel} />
            <Chip label="DECISIÓN" color={C.orange} bg={C.warnBg} />
            <Chip label="TRAZA" color={C.teal} bg={C.okBg} />
          </div>
          <div style={{ position: 'absolute', bottom: 60, left: 0, right: 0, textAlign: 'center', fontFamily: MONO, fontSize: 26, color: C.brown, opacity: fade(f, 290) }}>
            Maisa · HackSpain 2026 · 500 Sombras de Alberto
          </div>
        </div>
      </Frame>
    </Escena>
  );
};

// ── 2 · Problema ─────────────────────────────────────────────────────────────
// P: decidir parece fácil · S: las 2 alternativas ingenuas, tachadas · B: la norma + lo que Alberto necesita.
const Problema: React.FC = () => {
  const f = useFrameLocal(1);
  const [tS, tB] = TIEMPOS[1];
  const len = SCENES[1].frames;
  return (
    <Escena idx={1}>
      <Frame>
        <Voz idx={1} />
        <SectionKicker n="EL PROBLEMA" title="El problema de Alberto" />
        <Tiempos
          f={f} tS={tS} tB={tB} len={len}
          p={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 92 }}>Decidir parece fácil.</div>
              <div style={{ fontSize: 36, color: C.brown, marginTop: 20 }}>Cada factura acaba en una de estas:</div>
              <div style={{ marginTop: 44 }}>
                <Chip label="PAGAR" color={C.teal} bg={C.okBg} />
                <Chip label="NO_PAGAR" color={C.red} bg={C.badBg} />
                <Chip label="ESCALAR" color={C.orange} bg={C.warnBg} />
              </div>
            </div>
          }
          s={
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontSize: 36, color: C.brown, marginBottom: 32 }}>
                Dos atajos que no valen:
              </div>
              <div style={{ display: 'flex', gap: 36 }}>
                <Tachada titulo="LLM" motivo="lento y a veces inventa" f={f} delay={tS + 45} />
                <Tachada titulo="OCR clásico" motivo="se rinde con un escaneo malo" f={f} delay={tS + 85} />
              </div>
              <div style={{ ...rise(f, tS + 150), marginTop: 34, fontSize: 32, color: C.brown, fontStyle: 'italic' }}>
                …y sin evidencia, nadie responde por la decisión.
              </div>
            </div>
          }
          b={
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ ...rise(f, tB), fontFamily: DISPLAY, fontSize: 57, lineHeight: 1.25 }}>
                «Ante duda razonable, escalar antes que pagar.»
              </div>
              <div style={{
                ...rise(f, tB + 130), marginTop: 60, alignSelf: 'flex-start',
                border: `2px solid ${C.ink}`, background: C.panel, padding: '30px 44px',
              }}>
                <div style={{ fontSize: 28, color: C.brown, marginBottom: 16 }}>Lo que Alberto necesita:</div>
                <div style={{ ...rise(f, tB + 272), fontFamily: DISPLAY, fontSize: 44 }}>
                  precisión · rapidez · prueba
                </div>
              </div>
            </div>
          }
        />
      </Frame>
    </Escena>
  );
};

// ── 3 · Producto ─────────────────────────────────────────────────────────────
// P: ¿quién hace el trabajo nocturno? · S: los 5 pasos + captura rotando · B: solo miras cuando algo huele raro.
const CAPTURAS = [
  { src: shotDashboard, alt: 'Dashboard: contadores por resultado' },
  { src: shotRevision, alt: 'Revisión: candidatos y reglas lado a lado' },
  { src: shotLogs, alt: 'Trazas: eventos por factura' },
];

const Producto: React.FC = () => {
  const f = useFrameLocal(2);
  const [tS, tB] = TIEMPOS[2];
  const len = SCENES[2].frames;
  // Rotación de capturas dentro del tiempo S.
  const dur = tB - tS;
  const capIdx = Math.min(Math.floor((f - tS) / (dur / CAPTURAS.length)), CAPTURAS.length - 1);
  const cap = CAPTURAS[Math.max(0, capIdx)];
  const capF = Math.max(0, f - tS - Math.max(0, capIdx) * (dur / CAPTURAS.length));
  const pasos = [
    { t: 'Suelta los PDFs', s: 'se ingesta sola' },
    { t: 'Lote 24/7', s: 'sin prompts' },
    { t: 'Notificación al escritorio', s: 'solo cuando algo huele raro' },
    { t: 'Revisión humana', s: 'candidatos lado a lado' },
    { t: 'Sync con el servidor', s: 'sin depender de él: todo decide en local' },
  ];
  return (
    <Escena idx={2}>
      <Frame>
        <Voz idx={2} />
        <SectionKicker n="EL PRODUCTO" title="¿Quién hace el trabajo nocturno?" />
        <Tiempos
          f={f} tS={tS} tB={tB} len={len}
          p={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 92, textAlign: 'center', lineHeight: 1.2 }}>
                ¿Y quién hace el trabajo<br />de noche?
              </div>
              <div style={{ fontSize: 38, color: C.brown, marginTop: 30 }}>
                Una app de escritorio. No un script.
              </div>
            </div>
          }
          s={
            <div style={{ display: 'flex', gap: 40, alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                {pasos.map((p, i) => (
                  <div key={p.t} style={{
                    ...rise(f, tS + 15 + i * 60), display: 'flex', alignItems: 'baseline', gap: 16,
                    background: C.panel, border: `2px solid ${C.ink}`, padding: '13px 20px',
                    marginBottom: 12,
                  }}>
                    <div style={{
                      fontFamily: DISPLAY, fontSize: 24, background: C.ink, color: C.paper,
                      width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0, alignSelf: 'center',
                    }}>{i + 1}</div>
                    <div style={{ fontFamily: DISPLAY, fontSize: 25, width: 420, flexShrink: 0 }}>{p.t}</div>
                    <div style={{ fontSize: 25, color: i === 2 ? C.orange : C.brown, ...(i === 2 ? { fontWeight: 700 } : {}) }}>{p.s}</div>
                  </div>
                ))}
              </div>
              <div style={{ width: 600, ...rise(f, tS + 40) }}>
                <div style={{ border: `3px solid ${C.ink}`, background: C.panel, padding: 10 }}>
                  <img src={cap.src} alt={cap.alt} style={{ width: '100%', display: 'block', opacity: fade(capF, 0, 14) }} />
                </div>
                <div style={{ marginTop: 10, fontSize: 22, fontFamily: MONO, color: C.brown, textAlign: 'center' }}>
                  {cap.alt}
                </div>
              </div>
            </div>
          }
          b={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ ...rise(f, tB), fontFamily: DISPLAY, fontSize: 74, textAlign: 'center' }}>
                Tú solo miras cuando algo huele raro.
              </div>
              <div style={{
                ...rise(f, tB + 95), marginTop: 50, fontFamily: MONO, fontSize: 30,
                background: C.warnBg, border: `2px solid ${C.orange}`, color: C.ink,
                padding: '18px 34px',
              }}>
                ⏲ Notificación: «45 facturas a revisión»
              </div>
            </div>
          }
        />
      </Frame>
    </Escena>
  );
};

// ── 4 · Escalera ─────────────────────────────────────────────────────────────
// P: ¿quién lee una página difícil? · S: los 7 escalones (QUÉ/COSTE) · B: 94 % gratis y al instante + caveat.
const Escalera: React.FC = () => {
  const f = useFrameLocal(3);
  const [tS, tB] = TIEMPOS[3];
  const len = SCENES[3].frames;
  return (
    <Escena idx={3}>
      <Frame>
        <Voz idx={3} />
        <SectionKicker n="CÓMO LEE CADA PÁGINA" title="La escalera de confianza" />
        <Tiempos
          f={f} tS={tS} tB={tB} len={len}
          p={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 92, textAlign: 'center' }}>
                Una página difícil,<br />¿quién la lee?
              </div>
              <div style={{ fontSize: 38, color: C.brown, marginTop: 30 }}>
                Siete intentos, del más barato al más caro.
              </div>
            </div>
          }
          s={
            <div>
              <div style={{
                display: 'grid', gridTemplateColumns: '54px 1fr 180px',
                gap: 14, padding: '0 18px 8px', fontFamily: MONO, fontSize: 18, color: C.brown, letterSpacing: 1,
              }}>
                <div />
                <div>QUÉ CORRE</div>
                <div style={{ textAlign: 'right' }}>COSTE</div>
              </div>
              {ESCALERA.map((e, i) => (
                <div key={e.n} style={{
                  ...rise(f, tS + 10 + i * 78), display: 'grid', gridTemplateColumns: '54px 1fr 180px',
                  gap: 14, alignItems: 'center', background: i < 4 ? C.okBg : C.panel,
                  border: `2px solid ${C.ink}`, padding: '9px 18px', marginBottom: 7,
                }}>
                  <div style={{
                    fontFamily: DISPLAY, fontSize: 22, background: C.ink, color: C.paper,
                    width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>{e.n}</div>
                  <div>
                    <span style={{ fontWeight: 800, fontSize: 26, marginRight: 14 }}>{e.tech}</span>
                    <span style={{ fontSize: 21, color: C.brown }}>{e.sub}</span>
                  </div>
                  <div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 22, color: C.orange }}>{e.cost}</div>
                </div>
              ))}
              <div style={{ ...rise(f, tS + 480), marginTop: 12, fontSize: 22, color: C.brown, fontFamily: MONO, textAlign: 'right' }}>
                El VLM local (~4 GB RAM) solo arranca si el servidor está offline.
              </div>
            </div>
          }
          b={
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ ...rise(f, tB), display: 'flex', alignItems: 'baseline', gap: 26 }}>
                <div style={{ fontFamily: DISPLAY, fontSize: 170, color: C.teal, lineHeight: 1 }}>
                  {METRICS.textoUsablePct} %
                </div>
                <div style={{ fontSize: 42, maxWidth: 760 }}>
                  se resuelve gratis y al instante
                </div>
              </div>
              <div style={{
                ...rise(f, tB + 200), marginTop: 60, alignSelf: 'flex-start',
                border: `2px solid ${C.orange}`, background: C.warnBg, padding: '22px 34px', fontSize: 32,
              }}>
                <b>Caveat:</b> si un escalón falla, degrada con calma — <b>el lote nunca se para</b>.
              </div>
            </div>
          }
        />
      </Frame>
    </Escena>
  );
};

// ── 5 · Trazabilidad ─────────────────────────────────────────────────────────
// P: ¿por qué NO se paga esta? · S: 3 casos reales · B: auditable, nada se inventa.
const VerdictBadge: React.FC<{ result: string; size?: number }> = ({ result, size = 40 }) => {
  const color = result === 'PAGAR' ? C.teal : result === 'NO_PAGAR' ? C.red : C.orange;
  const bg = result === 'PAGAR' ? C.okBg : result === 'NO_PAGAR' ? C.badBg : C.warnBg;
  return (
    <span style={{ fontFamily: DISPLAY, fontSize: size, color, background: bg, border: `3px solid ${color}`, padding: '8px 28px' }}>
      {result}
    </span>
  );
};
const Regla: React.FC<{ code: string; state: 'PASS' | 'FAIL' | 'UNKNOWN'; f: number; delay?: number }> = ({ code, state, f, delay = 0 }) => {
  const color = state === 'PASS' ? C.teal : state === 'FAIL' ? C.red : C.orange;
  return (
    <div style={{ ...rise(f, delay), display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 25, padding: '7px 14px', borderBottom: `1px solid ${C.borderSoft}` }}>
      <span>{code}</span>
      <span style={{ color, fontWeight: 800 }}>{state}</span>
    </div>
  );
};

const Traza: React.FC = () => {
  const f = useFrameLocal(4);
  const [tS, tB] = TIEMPOS[4];
  const len = SCENES[4].frames;
  // Los 8 rule_ids reales (RULE_CODES) con el estado que salió en la corrida
  // real: lo que no está en `notPass` del caso salió PASS.
  const estados = (caso: { file_id: string; result: string; notPass: readonly string[]; nota: string }) =>
    REGLAS.map((code) => ({
      code,
      state: (caso.notPass.includes(`${code}:FAIL` as never) ? 'FAIL'
        : caso.notPass.includes(`${code}:UNKNOWN` as never) ? 'UNKNOWN' : 'PASS') as 'PASS' | 'FAIL' | 'UNKNOWN',
    }));
  const casos = [CASO_DUPLICADO, CASO_SCAN, CASO_ESCALAR];
  return (
    <Escena idx={4}>
      <Frame>
        <Voz idx={4} />
        <SectionKicker n="TRAZABILIDAD" title="¿Por qué NO se paga esta?" />
        <Tiempos
          f={f} tS={tS} tB={tB} len={len}
          p={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 92, textAlign: 'center' }}>
                ¿Por qué <span style={{ color: C.red }}>NO</span> se paga esta?
              </div>
              <div style={{ fontSize: 38, color: C.brown, marginTop: 30 }}>
                Sigamos tres decisiones reales.
              </div>
            </div>
          }
          s={
            <div style={{ display: 'flex', gap: 28 }}>
              {casos.map((caso, i) => (
                <div key={caso.file_id} style={{ flex: 1, ...rise(f, tS + 15 + i * 165) }}>
                  <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700 }}>{caso.file_id}</div>
                  <div style={{ margin: '12px 0 8px' }}><VerdictBadge result={caso.result} size={34} /></div>
                  <div style={{ border: `2px solid ${C.ink}`, background: C.panel }}>
                    {estados(caso).map((r, j) => <Regla key={r.code} code={r.code} state={r.state} f={f} delay={tS + 25 + i * 165 + j * 7} />)}
                  </div>
                  <div style={{ marginTop: 10, fontSize: 22, color: C.brown }}>{caso.nota}</div>
                </div>
              ))}
            </div>
          }
          b={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ ...rise(f, tB), fontFamily: DISPLAY, fontSize: 72, textAlign: 'center' }}>
                Nada se inventa. Todo se puede auditar.
              </div>
              <div style={{ marginTop: 50, display: 'flex', gap: 18 }}>
                {['sha256', 'extractor', 'confianza', 'config', 'latencia'].map((e, i) => (
                  <span key={e} style={{ ...rise(f, tB + 100 + i * 50), fontFamily: MONO, fontSize: 26, background: C.sand, border: `1px solid ${C.ink}`, padding: '10px 20px' }}>{e}</span>
                ))}
              </div>
              <div style={{ ...rise(f, tB + 390), marginTop: 26, fontSize: 28, color: C.brown }}>
                La evidencia viaja con cada decisión.
              </div>
            </div>
          }
        />
      </Frame>
    </Escena>
  );
};

// ── 6 · Reglas deterministas / ADRs ──────────────────────────────────────────
// P: una IA que decide distinto no es pagable · S: motor puro, byte a byte · B: ADR-06 + 8 ADRs + caveat.
const Adrs: React.FC = () => {
  const f = useFrameLocal(5);
  const [tS, tB] = TIEMPOS[5];
  const len = SCENES[5].frames;
  return (
    <Escena idx={5}>
      <Frame>
        <Voz idx={5} />
        <SectionKicker n="CÓMO DECIDE" title="Siempre la misma respuesta" />
        <Tiempos
          f={f} tS={tS} tB={tB} len={len}
          p={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 80, textAlign: 'center', lineHeight: 1.2 }}>
                Una IA que decide distinto cada vez<br />no es pagable.
              </div>
            </div>
          }
          s={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ ...rise(f, tS), fontFamily: DISPLAY, fontSize: 52, color: C.brown }}>MOTOR PURO</div>
              <div style={{
                ...rise(f, tS + 35), marginTop: 40, border: `2px solid ${C.ink}`, background: C.panel,
                padding: '40px 60px', fontFamily: DISPLAY, fontSize: 58, textAlign: 'center',
              }}>
                misma entrada ⇒ misma salida<br />
                <span style={{ color: C.teal }}>byte a byte</span>
              </div>
            </div>
          }
          b={
            <div style={{ display: 'flex', gap: 36, alignItems: 'stretch', justifyContent: 'center' }}>
              <div style={{
                ...rise(f, tB), flex: 1.3, border: `2px solid ${C.ink}`, background: C.okBg, padding: '28px 34px',
              }}>
                <div style={{ fontFamily: DISPLAY, fontSize: 34 }}>ADR-06 · Provenance</div>
                <div style={{ fontSize: 29, marginTop: 12 }}>
                  <b>86 falsos NO_PAGAR corregidos · 0 regresiones</b>
                </div>
                <div style={{ fontSize: 25, color: C.brown, marginTop: 10 }}>
                  Hoy el motor cita el candidato que eligió.
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24, flex: 1 }}>
                <div style={{ ...rise(f, tB + 106), border: `2px solid ${C.ink}`, background: C.panel, padding: '24px 30px' }}>
                  <div style={{ fontFamily: DISPLAY, fontSize: 64, lineHeight: 1 }}>8</div>
                  <div style={{ fontSize: 27, color: C.brown }}>decisiones escritas (ADRs)</div>
                </div>
                <div style={{ ...rise(f, tB + 216), border: `2px solid ${C.orange}`, background: C.warnBg, padding: '20px 30px', fontSize: 25 }}>
                  <b>Caveat:</b> la política FAIL→NO_PAGAR/ESCALAR es dato, no código.
                </div>
              </div>
            </div>
          }
        />
      </Frame>
    </Escena>
  );
};

// ── 7 · Resiliencia ──────────────────────────────────────────────────────────
// P: ¿y si algo cae a mitad del lote? · S: 4 drills PASS · B: reanudar no duplica + lema.
const Resiliencia: React.FC = () => {
  const f = useFrameLocal(6);
  const [tS, tB] = TIEMPOS[6];
  const len = SCENES[6].frames;
  return (
    <Escena idx={6}>
      <Frame>
        <Voz idx={6} />
        <SectionKicker n="RESILIENCIA" title="¿Y si algo se cae a mitad?" />
        <Tiempos
          f={f} tS={tS} tB={tB} len={len}
          p={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 92, textAlign: 'center' }}>
                ¿Y si algo cae<br />a mitad del lote?
              </div>
              <div style={{ fontSize: 38, color: C.brown, marginTop: 30 }}>
                Simulacros de desastre: cuatro de cuatro.
              </div>
            </div>
          }
          s={
            <div>
              {DRILLS.map((d, i) => (
                <div key={d.name} style={{
                  ...rise(f, tS + 12 + i * 16), display: 'flex', alignItems: 'center', gap: 24,
                  border: `2px solid ${C.ink}`, background: C.panel, padding: '18px 28px', marginBottom: 16, width: 1500,
                }}>
                  <span style={{ fontFamily: DISPLAY, fontSize: 32, color: C.teal }}>PASS</span>
                  <span style={{ fontFamily: MONO, fontSize: 29, fontWeight: 700, width: 500 }}>{d.name}</span>
                  <span style={{ fontSize: 28, color: C.brown }}>{d.detail}</span>
                </div>
              ))}
            </div>
          }
          b={
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ ...rise(f, tB), fontSize: 44 }}>
                Reanudar <b>nunca duplica</b> ni <b>re-factura</b>
                <span style={{ fontSize: 30, color: C.brown }}> — idempotencia por huella.</span>
              </div>
              {/* CLIENTE / SERVIDOR en bloque propio (1500×440): sustituye a las
                  dos líneas de sync que iban apiladas. Su `f` local arranca
                  cuando aparece, igual que el resto de entradas del beat. */}
              <div style={{ ...rise(f, tB + 55), marginTop: 26, display: 'flex', justifyContent: 'center' }}>
                <ClientServer f={f - tB - 55} />
              </div>
              <div style={{ ...rise(f, tB + 300), marginTop: 36, fontFamily: DISPLAY, fontSize: 88, lineHeight: 1.15 }}>
                Caerse no es opción:<br /><span style={{ color: C.orange }}>degradar.</span>
              </div>
            </div>
          }
        />
      </Frame>
    </Escena>
  );
};

// ── 8 · Escala y coste ───────────────────────────────────────────────────────
// P: ¿cuánto cuesta? · S: la fórmula con números · B: 2 min / 0 € + plan + cierre grande.
const Escala: React.FC = () => {
  const f = useFrameLocal(7);
  const [tS, tB] = TIEMPOS[7];
  const len = SCENES[7].frames;
  // Cierre: una sola entrada, la escala con muelle + fade. Antes se extendía
  // `rise(...)` (que emite translateY) y acto seguido `transform: scale(...)`
  // pisaba ese translateY, así que el desplazamiento nunca se veía; aquí el
  // fade replica el timing de `rise` y la escala sigue siendo la entrada real.
  const cierre = spring({ frame: Math.max(0, f - tB - 275), fps: 30, config: { damping: 13, mass: 0.7 } });
  const cierreIn = interpolate(f, [tB + 275, tB + 295], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic),
  });
  const filas: [string, string, string][] = [
    ['94 % del corpus', '0,00 €', 'medido'],
    ['El resto: tu CPU', `${METRICS.latenciaTotalS.toFixed(0)} s para ${METRICS.nArchivos} PDFs`, 'medido'],
    ['Cloud VLM', `solo páginas difíciles · ${METRICS.costeCloudEur.toFixed(2)} €`, 'medido'],
    ['10 000 facturas', '~40 min · 0 € en escalones 1–4', 'estimación'],
  ];
  return (
    <Escena idx={7}>
      <Frame>
        <Voz idx={7} />
        <SectionKicker n="ESCALA · COSTE" title="¿Cuánto cuesta?" />
        <Tiempos
          f={f} tS={tS} tB={tB} len={len}
          p={
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 110 }}>¿Cuánto cuesta?</div>
              <div style={{ fontSize: 38, color: C.brown, marginTop: 30 }}>
                Menos de lo que crees.
              </div>
            </div>
          }
          s={
            <div style={{ border: `2px solid ${C.ink}`, background: C.panel, width: 1500 }}>
              {filas.map(([k, v, tag], i) => (
                <div key={k} style={{ ...rise(f, tS + 12 + i * 35), display: 'grid', gridTemplateColumns: '520px 1fr 170px', alignItems: 'center', padding: '22px 30px', borderBottom: i < filas.length - 1 ? `1px solid ${C.borderSoft}` : 'none' }}>
                  <span style={{ fontSize: 30 }}>{k}</span>
                  <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700 }}>{v}</span>
                  <span style={{ fontSize: 22, color: tag === 'medido' ? C.teal : C.orange, fontFamily: MONO, textAlign: 'right' }}>{tag}</span>
                </div>
              ))}
            </div>
          }
          b={
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ ...rise(f, tB), display: 'flex', gap: 30, alignItems: 'baseline' }}>
                <span style={{ fontFamily: DISPLAY, fontSize: 88, color: C.teal }}>2 min</span>
                <span style={{ fontSize: 40 }}>para 500 facturas</span>
                <span style={{ fontFamily: DISPLAY, fontSize: 88, color: C.teal }}>0,00 €</span>
                <span style={{ fontSize: 40 }}>en la nube</span>
              </div>
              <div style={{ ...rise(f, tB + 110), marginTop: 28, fontSize: 29, color: C.brown }}>
                Más volumen: concurrencia · nuevo formato: un extractor y nada más.
              </div>
              <div style={{
                opacity: cierreIn, marginTop: 64, fontFamily: DISPLAY, fontSize: 87,
                transform: `scale(${cierre})`, transformOrigin: 'left center',
              }}>
                Alberto duerme. <span style={{ color: C.teal }}>Y paga lo justo.</span>
              </div>
            </div>
          }
        />
      </Frame>
    </Escena>
  );
};

export const FilemaidVideo: React.FC = () => {
  useFonts();
  return (
    <>
      {/* Pista externa (ver README → Audio), 180 s exactos ≈ 5400 frames, muy baja bajo la voz. */}
      <Audio src={staticFile('music_yt.wav')} volume={0.14} />
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
