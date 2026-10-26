import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';

/** Canvas creation precedes the first populated frame. */
export function RenderReady({ onReady }: { onReady: () => void }) {
  const reported = useRef(false);
  useFrame(({ gl }) => {
    if (!reported.current && gl.info.render.triangles > 0) {
      reported.current = true;
      onReady();
    }
  });
  return null;
}
