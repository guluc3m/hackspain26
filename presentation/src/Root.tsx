import React, { useEffect, useState } from "react";
import {
  AbsoluteFill, Composition, continueRender, delayRender, Sequence,
  staticFile,
} from "remotion";
import { cargarFuentes } from "./fuentes";
import {
  Cierre, Decisiones, Escalera, Numeros, Portada, Problema, Traza,
} from "./Secciones";
import { INK, PAPER, VIDEO } from "./theme";
import type { Datos } from "./datos";

// Duraciones (30 fps): portada 6s · problema 8s · escalera 12s · decisiones
// 14s · números 12s · traza 10s · cierre 8s = 75 s ≥ 45 s (T32).
const DUR = [180, 240, 360, 420, 360, 300, 240];
const TOTAL = DUR.reduce((a, b) => a + b, 0);

const Secciones: React.FC<{ datos: Datos }> = ({ datos }) => {
  const comps = [
    <Portada datos={datos} key="p" />,
    <Problema datos={datos} key="q" />,
    <Escalera datos={datos} key="e" />,
    <Decisiones datos={datos} key="d" />,
    <Numeros datos={datos} key="n" />,
    <Traza datos={datos} key="t" />,
    <Cierre datos={datos} key="c" />,
  ];
  let from = 0;
  const listado = comps.map((sec, i) => {
    const f = from;
    from += DUR[i];
    return (
      <Sequence key={i} from={f} durationInFrames={DUR[i]}
        name={`sección ${i + 1}`}>
        {sec}
      </Sequence>
    );
  });
  return (
    <AbsoluteFill style={{ background: PAPER, color: INK }}>
      {listado}
    </AbsoluteFill>
  );
};

const ConDatos: React.FC<{ children: (d: Datos) => React.ReactNode }> = ({
  children,
}) => {
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    const h = delayRender("cargando datos.json");
    fetch(staticFile("datos.json"))
      .then((r) => r.json())
      .then((d: Datos) => {
        setDatos(d);
        continueRender(h);
      })
      .catch((e) => {
        setError(e);
        continueRender(h);
      });
  }, []);
  if (error) {
    return (
      <AbsoluteFill style={{ background: PAPER, color: INK, fontSize: 40 }}>
        datos.json no generado — `uv run python -m albertitos.presentacion`
      </AbsoluteFill>
    );
  }
  if (!datos) return null;
  return <>{children(datos)}</>;
};

export const RemotionRoot: React.FC = () => {
  useEffect(() => {
    cargarFuentes();
  }, []);
  return (
    <>
      <Composition
        id="Presentacion"
        durationInFrames={TOTAL}
        fps={VIDEO.fps}
        width={VIDEO.width}
        height={VIDEO.height}
        component={function () {
          return (
            <ConDatos>{(d: Datos) => <Secciones datos={d} />}</ConDatos>
          );
        }}
        defaultProps={{}}
      />
      <Composition
        id="Portada"
        durationInFrames={90}
        fps={VIDEO.fps}
        width={VIDEO.width}
        height={VIDEO.height}
        component={function () {
          return (
            <ConDatos>{(d: Datos) => <Portada datos={d} />}</ConDatos>
          );
        }}
        defaultProps={{}}
      />
    </>
  );
};
