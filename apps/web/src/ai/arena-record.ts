import type { PolicyPosition, PolicyRoot } from '../inference/policy-session';
import type { ModelCompleted } from './arena-model';
import type { SearchConfig, SearchSuccess } from './search-protocol';
import type { ArenaOptions } from './arena-controller';
export function arenaConditions(options: ArenaOptions) {
  const agent = (side: 'b' | 'w') => {
    if ((side === 'b' && options.mode === 'h-r') || (side === 'w' && options.mode === 'r-h')) return { controller: 'human' };
    const difficulty = side === 'b' ? options.bDifficulty : options.wDifficulty;
    if (difficulty !== 'model') return { controller: 'ai', difficulty, limits: options.limits, seed: options.seed, seedRule: 'uint32(baseSeed + rootRevision)' };
    const model = side === 'b' ? options.bModel : options.wModel;
    if (!model) throw new Error('selected model is missing');
    const { sourceId, repo, revision, sourceCommit, license, selection } = model;
    return { controller: 'ai', difficulty, model: { sourceId, repo, revision, sourceCommit, license, selection }, decision: 'legal-policy-argmax-smallest-action-tie' };
  };
  return structuredClone({ mode: options.mode, b: agent('b'), w: agent('w') });
}

type Completed = (SearchSuccess & { roundTripMs: number }) | ModelCompleted;
export interface AiObservation { root: PolicyRoot; reply: Completed; search?: { seed: number; limits: SearchConfig } }
function history(recordJson: string): { identity: string; moves: string[] } {
  const record = JSON.parse(recordJson) as { initial: string; ruleset_id: string; moves: string[] };
  if (typeof record.initial !== 'string' || typeof record.ruleset_id !== 'string' || !Array.isArray(record.moves) || record.moves.some(move => typeof move !== 'string')) throw new Error('invalid game history');
  return { identity: JSON.stringify([record.ruleset_id, record.initial]), moves: record.moves };
}
/** One retained game branch, with provenance only for successfully applied AI moves. */
export class ArenaJournal {
  private identity = '';
  private moves: string[] = [];
  private observations = new Map<number, AiObservation>();
  clear() { this.identity = ''; this.moves = []; this.observations.clear(); }
  reconcile(recordJson: string) {
    const next = history(recordJson);
    if (next.identity !== this.identity) this.clear();
    let shared = 0;
    while (shared < this.moves.length && shared < next.moves.length && this.moves[shared] === next.moves[shared]) shared++;
    for (const cursor of this.observations.keys()) if (cursor >= shared) this.observations.delete(cursor);
    this.identity = next.identity; this.moves = next.moves.slice();
  }
  accept(position: PolicyPosition, search: { seed: number; limits: SearchConfig }, value: Completed) {
    // Discard any old future branch before attributing the newly accepted move.
    const record = JSON.parse(position.recordJson) as { moves: string[] };
    record.moves = record.moves.slice(0, position.cursor);
    this.reconcile(JSON.stringify(record));
    const { revision, cursor, side, hash, ruleset } = position;
    const root = { revision, cursor, side, hash, ruleset };
    const common = { ...root, requestId: value.requestId, roundTripMs: value.roundTripMs, result: value.result };
    const reply: Completed = value.kind === 'model-result'
      ? { ...common, kind: 'model-result', result: value.result, model: value.model, validation: value.validation, inferenceMs: value.inferenceMs }
      : { ...common, schema: 1, kind: 'result', result: value.result, difficulty: value.difficulty, metrics: value.metrics };
    this.observations.set(cursor, structuredClone({ root, reply, ...(value.kind === 'model-result' ? {} : { search }) }));
    this.moves.push(value.result.bestMove!);
  }
  snapshot(recordJson: string, cursor: number): AiObservation[] {
    this.reconcile(recordJson);
    return structuredClone([...this.observations.entries()].filter(([ply]) => ply < cursor).sort(([a], [b]) => a - b).map(([, value]) => value));
  }
}
