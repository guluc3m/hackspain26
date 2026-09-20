// Entry point DESECHABLE solo para revisar <ClientServer /> a pantalla completa.
//   npx remotion still src/diagram-preview.tsx diagram out/cs-f0.png --frame=0
import React from 'react';
import { AbsoluteFill, Composition, registerRoot, useCurrentFrame } from 'remotion';
import { C } from './scenes';
import { useFonts } from './fonts';
import { ClientServer } from './ClientServer';

const DiagramPreview: React.FC = () => {
  useFonts();
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{
      background: C.paper,
      color: C.ink,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      <ClientServer f={f} />
    </AbsoluteFill>
  );
};

const RemotionRoot: React.FC = () => (
  <Composition
    id="diagram"
    component={DiagramPreview}
    durationInFrames={150}
    fps={30}
    width={1920}
    height={1080}
  />
);

registerRoot(RemotionRoot);
