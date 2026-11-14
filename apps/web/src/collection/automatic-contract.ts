import { agent, hex, integer, keys, object, result, type GameSubmission } from './contract';

export const AUTOMATIC_POLICY = 'automatic-game-v2';
export interface AutomaticSubmission {
  schema: 2; policy: typeof AUTOMATIC_POLICY; gameId: string; requestId: string; version: number;
  state: 'progress' | 'finished' | 'aborted'; applicationCommit: string;
  mode: GameSubmission['mode']; conditionsScope: 'game-start';
  selectedAgents: GameSubmission['selectedAgents']; record: GameSubmission['record'];
}
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(v);

/** Structural admission, not a claim that Rust has replayed or verified the game. */
export function isAutomaticSubmission(v: unknown): v is AutomaticSubmission {
  if (!object(v) || !keys(v, 'schema,policy,gameId,requestId,version,state,applicationCommit,mode,conditionsScope,selectedAgents,record')) return false;
  if (v.schema !== 2 || v.policy !== AUTOMATIC_POLICY || v.conditionsScope !== 'game-start' || !hex(v.applicationCommit, 40) || !uuid(v.gameId) || !uuid(v.requestId) || !integer(v.version, 1, 1e9)) return false;
  if (!['r-r', 'h-r', 'r-h'].includes(String(v.mode)) || !object(v.selectedAgents) || !keys(v.selectedAgents, 'b,w') || !agent(v.selectedAgents.b) || !agent(v.selectedAgents.w)) return false;
  if ((v.selectedAgents.b.kind === 'human') !== (v.mode === 'h-r') || (v.selectedAgents.w.kind === 'human') !== (v.mode === 'r-h')) return false;
  const r = v.record;
  if (!object(r) || !keys(r, 'ruleset_id,initial,moves,result,termination') || r.ruleset_id !== 'voxelshogi-standard-v1') return false;
  if (typeof r.initial !== 'string' || r.initial.length < 1 || r.initial.length > 4096 || !/^[0-9PLNSGBRKplnsgbrkw+|/ -]+$/.test(r.initial)) return false;
  if (!Array.isArray(r.moves) || r.moves.length < 1 || r.moves.length > 2048 || r.moves.some(m => typeof m !== 'string' || !/^(?:[1-9]{6}\+?|[PLNSGBR]\*[1-9]{3})$/.test(m))) return false;
  if (!result(r.result) || !(r.termination === null || ['Resignation', 'MaxPlies', 'Abandoned'].includes(String(r.termination)))) return false;
  if (v.state === 'progress') return r.result === null && r.termination === null;
  if (v.state === 'finished') return r.result !== null && r.termination !== 'Abandoned';
  return v.state === 'aborted' && r.result === null && r.termination === 'Abandoned';
}
