// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useTrailMotion } from '../src/renderer/useTrailMotion';

const fake = vi.hoisted(() => ({ frame: null as null | ((state: { invalidate: () => void }, delta: number) => void) }));
vi.mock('@react-three/fiber', () => ({ useFrame: (frame: typeof fake.frame) => { fake.frame = frame; } }));
afterEach(cleanup);

it('starts at the origin after a long idle instead of skipping the visible animation', () => {
  const set = vi.fn(), invalidate = vi.fn();
  renderHook(() => useTrailMotion([0, 0, 2.2], [0, 1.7, 1.1], { current: { position: { set } } }));
  act(() => fake.frame!({ invalidate }, 120));
  expect(set.mock.calls[0]).toEqual([0, 0.45, 2.2]);
  expect(invalidate).toHaveBeenCalledTimes(1);
});

it('animates to the real destination once, then stops requesting frames while paused', () => {
  const set = vi.fn(), invalidate = vi.fn();
  const target = { current: { position: { set } } };
  renderHook(() => useTrailMotion([0, 0, 2.2], [0, 1.7, 1.1], target));
  act(() => fake.frame!({ invalidate }, 0));
  act(() => fake.frame!({ invalidate }, 0.25));
  expect(set.mock.calls[1]![0]).toBe(0);
  expect(set.mock.calls[1]![1]).toBeCloseTo(0.96); // 30% of 1.7 plus 0.45
  expect(set.mock.calls[1]![2]).toBeCloseTo(1.87);
  expect(invalidate).toHaveBeenCalledTimes(2);
  act(() => fake.frame!({ invalidate }, 10));
  expect(set.mock.calls.at(-1)![1]).toBeCloseTo(2.15);
  expect(set.mock.calls.at(-1)![2]).toBeCloseTo(1.1);
  act(() => fake.frame!({ invalidate }, 1));
  expect(invalidate).toHaveBeenCalledTimes(2); // never restart or loop on a stopped position
});
