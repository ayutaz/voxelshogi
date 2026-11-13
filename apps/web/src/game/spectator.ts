import { coordsOf, parseMove, type Slice } from './model';
import type { LayerView } from '../renderer/Board3D';

/** Only the move at the displayed cursor may guide the view, never the future tail. */
export function followView(lastMove: string | null, enabled: boolean, slice: Slice, layers: LayerView) {
  if (!enabled || !lastMove) return { slice, layers };
  const z = coordsOf(parseMove(lastMove).to).z;
  return { slice: { axis: 'z' as const, index: z }, layers: { ...layers, z } };
}

/** A promoted/plain pair is one square in Selection.targets. */
export function layerTargets(targets: Iterable<number>): number[] {
  const counts = Array<number>(9).fill(0);
  for (const target of targets) counts[coordsOf(target).z]! += 1;
  return counts;
}
