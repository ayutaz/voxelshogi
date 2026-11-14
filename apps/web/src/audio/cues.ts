import type { Color } from '../game/model';
import type { PresentationEvent } from '../game/presentation';

export type SoundCue = 'move' | 'capture' | 'capture-against' | 'promotion' | 'check' | 'end' | 'win' | 'defeat';
export function cueFor(event: PresentationEvent, human: Color | null): SoundCue | null {
  if (event.kind === 'clear') return null;
  if (event.kind !== 'forward' && event.result) {
    if (event.result.kind === 'draw' || human === null) return 'end';
    return event.result.winner === human ? 'win' : 'defeat';
  }
  if (event.kind === 'end') return 'end';
  if (event.kind === 'move' && event.check) return 'check';
  if (event.capture) return event.kind === 'move' && human !== null && event.mover !== human ? 'capture-against' : 'capture';
  if (event.kind === 'move' && event.promotion) return 'promotion';
  return 'move';
}
