import type { Color } from './model';
import type { ResultInfo } from './store';

export type PresentationInput =
  | { kind: 'move' | 'forward'; mover: Color; capture: boolean; promotion: boolean; check: boolean; result: ResultInfo | null }
  | { kind: 'end'; result: ResultInfo | null }
  | { kind: 'clear' };
export type PresentationEvent = PresentationInput & { id: string };
