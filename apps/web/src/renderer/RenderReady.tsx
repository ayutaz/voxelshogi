import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';

/** Canvas creation precedes the first populated frame. */
export function RenderReady({ onReady }: { onReady: () => void }) {
  const reported = useRef(false);
  useFrame(({ gl, invalidate }) => {
    // useFrame runs before drawing. A demand canvas needs one more frame to
    // observe the geometry rendered by the preceding frame.
    if (!reported.current && gl.info.render.triangles === 0) invalidate();
    if (!reported.current && gl.info.render.triangles > 0) {
      reported.current = true;
      onReady();
    }
  });
  return null;
}
