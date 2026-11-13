import { describe, expect, it } from 'vitest';
import { followView, layerTargets } from '../src/game/spectator';

const slice = { axis: 'x' as const, index: 2 };
const layers = { mode: 'focus' as const, z: 4, dim: 0.18 };

describe('following the move at the displayed history cursor', () => {
  it.each([
    ['575565', 4], // Black: layer V → V
    ['535545', 4], // White: layer V → V
    ['575566', 5], // Black: layer V → VI
    ['535544', 3], // White: layer V → IV
    ['575565', 4], // undo to the preceding move, not the future move
    ['535544', 3], // redo uses the move now visible
  ])('follows %s to destination layer %i', (move, z) => {
    expect(followView(move, true, slice, layers)).toEqual({ slice: { axis: 'z', index: z }, layers: { ...layers, z } });
  });
  it('keeps the manual cross-section with follow OFF', () => {
    expect(followView('575566', false, slice, layers)).toEqual({ slice, layers });
  });
  it('keeps the manually chosen layer until following is requested again', () => {
    const manual = { axis: 'z' as const, index: 1 };
    expect(followView('575566', false, manual, layers).slice).toEqual(manual);
    expect(followView('575566', true, manual, layers).slice).toEqual({ axis: 'z', index: 5 });
    expect(followView(null, true, manual, layers).slice).toEqual(manual);
  });
});

it('counts unique destination squares per layer, without double-counting promotion choices', () => {
  const targets = new Map([[324, {}], [405, {}], [406, {}], [0, {}]]);
  expect(layerTargets(targets.keys())).toEqual([1, 0, 0, 0, 1, 2, 0, 0, 0]);
  expect(layerTargets([])).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0]);
});
