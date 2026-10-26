// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { RenderReady } from '../src/renderer/RenderReady';

let frame: (state: { gl: { info: { render: { triangles: number } } }; invalidate: () => void }) => void;
vi.mock('@react-three/fiber', () => ({ useFrame: (callback: typeof frame) => { frame = callback; } }));
afterEach(cleanup);

it('reports readiness only after the renderer drew geometry and only once per mount', () => {
  const ready = vi.fn();
  const mounted = render(<RenderReady onReady={ready} />);
  act(() => frame({ gl: { info: { render: { triangles: 0 } } }, invalidate: vi.fn() }));
  expect(ready).not.toHaveBeenCalled();
  act(() => frame({ gl: { info: { render: { triangles: 372 } } }, invalidate: vi.fn() }));
  expect(ready).toHaveBeenCalledTimes(1);
  act(() => frame({ gl: { info: { render: { triangles: 372 } } }, invalidate: vi.fn() }));
  expect(ready).toHaveBeenCalledTimes(1);
  mounted.unmount();
  render(<RenderReady onReady={ready} />);
  act(() => frame({ gl: { info: { render: { triangles: 0 } } }, invalidate: vi.fn() }));
  expect(ready).toHaveBeenCalledTimes(1);
  act(() => frame({ gl: { info: { render: { triangles: 1 } } }, invalidate: vi.fn() }));
  expect(ready).toHaveBeenCalledTimes(2);
});

it('requests another frame until geometry is visible, then stops requesting frames', () => {
  const ready = vi.fn(), invalidate = vi.fn();
  render(<RenderReady onReady={ready} />);
  act(() => frame({ gl: { info: { render: { triangles: 0 } } }, invalidate }));
  expect(invalidate).toHaveBeenCalledTimes(1);
  act(() => frame({ gl: { info: { render: { triangles: 372 } } }, invalidate }));
  expect(ready).toHaveBeenCalledTimes(1);
  expect(invalidate).toHaveBeenCalledTimes(1);
  act(() => frame({ gl: { info: { render: { triangles: 372 } } }, invalidate }));
  expect(invalidate).toHaveBeenCalledTimes(1);
});
