import type { ResultInfo } from './store';

/** The end of the retained record, irrespective of the viewed history cursor. */
export function recordOutcome(recordJson: string): ResultInfo | null {
  const value = JSON.parse(recordJson) as { result?: { Win?: { winner: 'Black' | 'White'; reason: 'Checkmate' | 'Resignation' | 'PerpetualCheck' }; Draw?: { reason: 'Repetition' | 'MaxPlies' } } | null };
  if (!value.result) return null;
  if (value.result.Win) return { kind: 'win', winner: value.result.Win.winner === 'Black' ? 'b' : 'w', reason: value.result.Win.reason };
  if (value.result.Draw) return { kind: 'draw', reason: value.result.Draw.reason };
  throw new Error('unknown terminal record result');
}
