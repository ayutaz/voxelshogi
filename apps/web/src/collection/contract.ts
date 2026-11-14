export const COLLECTION_CONSENT = 'game-research-v1';
export const MAX_GAME_BYTES = 256 * 1024;
export type CollectionAgent =
  | { kind: 'human' }
  | { kind: 'easy'; seed: number }
  | { kind: 'normal'; seed: number; maxDepth: number; maxNodes: number; maxTimeMs: number }
  | { kind: 'model'; modelId: string; repo: string; revision: string; sourceCommit: string; license: string;
      precision: 'fp32' | 'fp16' | 'int8'; backend: 'wasm' | 'webgpu'; packageHash: string };
export interface GameSubmission {
  schema: 1; requestId: string; consent: typeof COLLECTION_CONSENT; ending: 'finished' | 'aborted';
  applicationCommit: string; mode: 'r-r' | 'h-r' | 'r-h'; conditionsScope: 'selected-at-submission';
  selectedAgents: { b: CollectionAgent; w: CollectionAgent };
  record: { ruleset_id: 'voxelshogi-standard-v1'; initial: string; moves: string[]; result: unknown; termination: string | null };
}
type ObjectValue = Record<string, unknown>;
export function object(value: unknown): value is ObjectValue { return value !== null && typeof value === 'object' && !Array.isArray(value); }
export function keys(value: ObjectValue, expected: string): boolean { const names = expected.split(','); return Object.keys(value).length === names.length && names.every(name => Object.hasOwn(value, name)); }
export function integer(value: unknown, min: number, max: number): value is number { return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max; }
export const hex = (value: unknown, count: number) => typeof value === 'string' && new RegExp(`^[0-9a-f]{${count}}$`).test(value);
export function agent(value: unknown): value is CollectionAgent {
  if (!object(value)) return false;
  if (value.kind === 'human') return keys(value, 'kind');
  if (value.kind === 'easy') return keys(value, 'kind,seed') && integer(value.seed, 0, 4294967295);
  if (value.kind === 'normal') return keys(value, 'kind,seed,maxDepth,maxNodes,maxTimeMs') && integer(value.seed, 0, 4294967295) && integer(value.maxDepth, 1, 64) && integer(value.maxNodes, 1, 1e9) && integer(value.maxTimeMs, 1, 60000);
  return value.kind === 'model' && keys(value, 'kind,modelId,repo,revision,sourceCommit,license,precision,backend,packageHash') &&
    typeof value.modelId === 'string' && /^[A-Za-z0-9._-]{1,128}$/.test(value.modelId) &&
    typeof value.repo === 'string' && /^voxelshogi\/[A-Za-z0-9._-]{1,128}$/.test(value.repo) &&
    hex(value.revision, 40) && hex(value.sourceCommit, 40) && hex(value.packageHash, 64) &&
    typeof value.license === 'string' && /^[A-Za-z0-9.-]{1,64}$/.test(value.license) &&
    ['fp32', 'fp16', 'int8'].includes(String(value.precision)) && ['wasm', 'webgpu'].includes(String(value.backend));
}
export function result(value: unknown): boolean {
  if (value === null) return true;
  if (!object(value)) return false;
  if (keys(value, 'Win') && object(value.Win) && keys(value.Win, 'winner,reason')) return ['Black', 'White'].includes(String(value.Win.winner)) && ['Checkmate', 'Resignation', 'PerpetualCheck'].includes(String(value.Win.reason));
  return keys(value, 'Draw') && object(value.Draw) && keys(value.Draw, 'reason') && ['Repetition', 'MaxPlies'].includes(String(value.Draw.reason));
}

/** Structural admission only. Full rules/outcome replay is a separate Rust job. */
export function isGameSubmission(value: unknown): value is GameSubmission {
  if (!object(value) || !keys(value, 'schema,requestId,consent,ending,applicationCommit,mode,conditionsScope,selectedAgents,record')) return false;
  if (value.schema !== 1 || value.consent !== COLLECTION_CONSENT || value.conditionsScope !== 'selected-at-submission' || !hex(value.applicationCommit, 40)) return false;
  if (typeof value.requestId !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value.requestId)) return false;
  if (!['finished', 'aborted'].includes(String(value.ending)) || !['r-r', 'h-r', 'r-h'].includes(String(value.mode))) return false;
  if (!object(value.selectedAgents) || !keys(value.selectedAgents, 'b,w') || !agent(value.selectedAgents.b) || !agent(value.selectedAgents.w)) return false;
  if ((value.selectedAgents.b.kind === 'human') !== (value.mode === 'h-r') || (value.selectedAgents.w.kind === 'human') !== (value.mode === 'r-h')) return false;
  const r = value.record;
  if (!object(r) || !keys(r, 'ruleset_id,initial,moves,result,termination') || r.ruleset_id !== 'voxelshogi-standard-v1') return false;
  if (typeof r.initial !== 'string' || r.initial.length < 1 || r.initial.length > 4096 || !/^[0-9PLNSGBRKplnsgbrkw+|/ -]+$/.test(r.initial)) return false;
  if (!Array.isArray(r.moves) || r.moves.length > 2048 || r.moves.some(move => typeof move !== 'string' || !/^(?:[1-9]{6}\+?|[PLNSGBR]\*[1-9]{3})$/.test(move))) return false;
  if (!result(r.result) || !(r.termination === null || ['Resignation', 'MaxPlies', 'Abandoned'].includes(String(r.termination)))) return false;
  return value.ending === 'finished' ? r.result !== null && r.termination !== 'Abandoned' : r.result === null && r.termination === 'Abandoned';
}
