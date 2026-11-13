import { useRef, type RefObject } from 'react';
import { useFrame } from '@react-three/fiber';

type Point = [number, number, number];
type Target = { position: { set: (x: number, y: number, z: number) => unknown } };

/** Demand-rendered once per move; a paused game must not animate forever. */
export function useTrailMotion(start: Point, end: Point, ball: RefObject<Target | null>) {
  const progress = useRef(0);
  const started = useRef(false);
  useFrame(({ invalidate }, delta) => {
    // Demand-rendered canvases include idle time in their first delta.
    // Start a new move at its origin, then advance using subsequent frames.
    if (started.current) progress.current = Math.min(1, progress.current + delta * 1.2);
    started.current = true;
    const t = progress.current;
    ball.current?.position.set(start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t + 0.45, start[2] + (end[2] - start[2]) * t);
    if (progress.current < 1) invalidate();
  });
}
