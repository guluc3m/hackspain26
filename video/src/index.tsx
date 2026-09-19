import { registerRoot, Composition } from 'remotion';
import { FilemaidVideo } from './FilemaidVideo';
import { SCENES, FPS, WIDTH, HEIGHT } from './scenes';

export const RemotionRoot = () => (
  <Composition
    id="filemaid"
    component={FilemaidVideo}
    durationInFrames={SCENES.reduce((a, s) => a + s.frames, 0)}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
  />
);

registerRoot(RemotionRoot);
