import type { Snapshot } from './store';
/** Rendering does not need legal moves or a live game session. */
export type BoardSnapshot = Pick<Snapshot, 'board' | 'lastMove' | 'inCheck' | 'kingSquare'>;
