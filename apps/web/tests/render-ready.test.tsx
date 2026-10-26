// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { RenderReady } from '../src/renderer/RenderReady';

let frame: (state: { gl: { info: { render: { triangles: number } } } }) => void;
vi.mock('@react-three/fiber', () => ({ useFrame: (callback: typeof frame) => { frame = callback; } }));
afterEach(cleanup);

it('reports readiness only after the renderer drew geometry and only once per mount', () => {
  const ready = vi.fn();
  const mounted = render(<RenderReady onReady={ready} />);
  act(() => frame({ gl: { info: { render: { triangles: 0 } } } }));
  expect(ready).not.toHaveBeenCalled();
  act(() => frame({ gl: { info: { render: { triangles: 372 } } } }));
  expect(ready).toHaveBeenCalledTimes(1);
  act(() => frame({ gl: { info: { render: { triangles: 372 } } } }));
  expect(ready).toHaveBeenCalledTimes(1);
  mounted.unmount();
  render(<RenderReady onReady={ready} />);
  act(() => frame({ gl: { info: { render: { triangles: 0 } } } }));
  expect(ready).toHaveBeenCalledTimes(1);
  act(() => frame({ gl: { info: { render: { triangles: 1 } } } }));
  expect(ready).toHaveBeenCalledTimes(2);
});
