import type { Color } from '../game/model';

export const SEARCH_RULESET = 'voxelshogi-standard-v1';
export interface SearchConfig {
  maxDepth: number;
  maxNodes?: number | null;
  maxTimeMs?: number | null;
  maxGamePly?: number | null;
  options?: { iterativeDeepening?: boolean; moveOrdering?: boolean; transpositionTable?: boolean; tableCapacity?: number };
}
export interface RootIdentity {
  schema: 1;
  requestId: number;
  revision: number;
  ruleset: string;
  cursor: number;
  hash: string;
  side: Color;
  difficulty: 'easy' | 'normal';
}
export interface SearchRequest extends RootIdentity {
  kind: 'search';
  recordJson: string;
  seed: number;
  limits: SearchConfig;
}
export type SearchInput = Omit<SearchRequest, 'requestId'>;
export interface AiResult {
  schema: 1;
  bestMove: string | null;
  score: number | null;
  completedDepth: number;
  nodes: string;
  lastIterationNodes: string;
  ttHits: string;
  stopReason: 'depth' | 'nodes' | 'time' | 'terminal' | 'random';
}
export interface SearchSuccess extends RootIdentity {
  kind: 'result';
  result: AiResult;
  metrics: { initMs: number; replayMs: number; searchMs: number; totalMs: number };
}
export interface SearchFailure extends RootIdentity {
  kind: 'error';
  code: 'input' | 'busy' | 'initialization' | 'execution';
  message: string;
}
export type SearchReply = SearchSuccess | SearchFailure;
export interface WorkerPort {
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: ErrorEvent) => void) | null;
  onmessageerror: ((event: MessageEvent) => void) | null;
  postMessage(message: SearchRequest): void;
  terminate(): void;
}

function check(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
function object(value: unknown): Record<string, unknown> {
  check(typeof value === 'object' && value !== null && !Array.isArray(value), 'expected object');
  return value as Record<string, unknown>;
}
const integer = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= min && v <= max;
const move = (v: unknown): v is string => typeof v === 'string' && /^(?:[1-9]{6}\+?|[PLNSGBR]\*[1-9]{3})$/.test(v);
function keys(o: Record<string, unknown>, allowed: string[]) {
  check(Object.keys(o).every((key) => allowed.includes(key)), 'unknown field');
}

export function validateConfig(value: unknown): asserts value is SearchConfig {
  const c = object(value);
  keys(c, ['maxDepth', 'maxNodes', 'maxTimeMs', 'maxGamePly', 'options']);
  check(integer(c.maxDepth, 0, 64), 'invalid depth');
  check(c.maxNodes == null || integer(c.maxNodes), 'invalid nodes');
  check(c.maxGamePly == null || integer(c.maxGamePly, 0, 0xffff_ffff), 'invalid game ply');
  check(c.maxTimeMs == null || (typeof c.maxTimeMs === 'number' && Number.isFinite(c.maxTimeMs) && c.maxTimeMs >= 0 && c.maxTimeMs <= Number.MAX_SAFE_INTEGER), 'invalid time');
  if (c.options !== undefined) {
    const o = object(c.options);
    keys(o, ['iterativeDeepening', 'moveOrdering', 'transpositionTable', 'tableCapacity']);
    for (const key of ['iterativeDeepening', 'moveOrdering', 'transpositionTable']) check(o[key] === undefined || typeof o[key] === 'boolean', 'invalid search option');
    check(o.tableCapacity === undefined || integer(o.tableCapacity, 0, 1_000_000), 'invalid table capacity');
  }
  check(new TextEncoder().encode(JSON.stringify(value)).length <= 4096, 'config too large');
}

export function parseRequest(value: unknown): SearchRequest {
  const r = object(value);
  keys(r, ['schema', 'kind', 'requestId', 'revision', 'ruleset', 'cursor', 'hash', 'side', 'difficulty', 'recordJson', 'seed', 'limits']);
  check(r.schema === 1 && r.kind === 'search', 'unsupported request schema');
  check(integer(r.requestId, 1) && integer(r.revision), 'invalid request identity');
  check(r.ruleset === SEARCH_RULESET, 'unsupported ruleset');
  check(integer(r.cursor, 0, 20_000), 'invalid cursor');
  check(typeof r.hash === 'string' && /^[0-9a-f]{16}$/.test(r.hash), 'invalid root hash');
  check(r.side === 'b' || r.side === 'w', 'invalid side');
  check(r.difficulty === 'easy' || r.difficulty === 'normal', 'invalid difficulty');
  check(integer(r.seed, 0, 0xffff_ffff), 'invalid seed');
  check(typeof r.recordJson === 'string' && r.recordJson.length <= 4 * 1024 * 1024 && new TextEncoder().encode(r.recordJson).length <= 4 * 1024 * 1024, 'invalid record size');
  validateConfig(r.limits);
  return r as unknown as SearchRequest;
}

/** Error identity is best effort for malformed requests, exact for valid ones. */
export function identity(value: unknown): RootIdentity {
  const r = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
  return { schema: 1, requestId: integer(r.requestId, 1) ? r.requestId : 0,
    revision: integer(r.revision) ? r.revision : 0, ruleset: typeof r.ruleset === 'string' ? r.ruleset : '',
    cursor: integer(r.cursor) ? r.cursor : 0, hash: typeof r.hash === 'string' ? r.hash : '',
    side: r.side === 'w' ? 'w' : 'b', difficulty: r.difficulty === 'easy' ? 'easy' : 'normal' };
}

export function parseAiResult(value: unknown, request: SearchRequest): AiResult {
  const r = object(value);
  check(r.schema === 1 && integer(r.completedDepth, 0, request.limits.maxDepth), 'invalid result depth');
  check(r.score === null || integer(r.score, -1_000_000, 1_000_000), 'invalid score');
  check(r.completedDepth === 0 || r.score !== null, 'missing completed score');
  const count = (n: unknown): n is string => typeof n === 'string' && /^(0|[1-9][0-9]{0,19})$/.test(n) && BigInt(n) <= 18_446_744_073_709_551_615n;
  check(count(r.nodes) && count(r.lastIterationNodes) && count(r.ttHits), 'invalid node counts');
  check(BigInt(r.lastIterationNodes) <= BigInt(r.nodes) && BigInt(r.ttHits) <= BigInt(r.nodes), 'inconsistent node counts');
  check(request.limits.maxNodes == null || BigInt(r.nodes) <= BigInt(request.limits.maxNodes), 'node limit exceeded');
  check(['depth', 'nodes', 'time', 'terminal', 'random'].includes(r.stopReason as string), 'invalid stop reason');
  check(r.stopReason === 'terminal' ? r.bestMove === null : move(r.bestMove), 'invalid best move');
  check(r.stopReason !== 'random' || request.difficulty === 'easy', 'unexpected random fallback');
  return r as unknown as AiResult;
}

export function parseReply(value: unknown, request: SearchRequest): SearchReply {
  const r = object(value);
  for (const key of ['schema', 'requestId', 'revision', 'ruleset', 'cursor', 'hash', 'side', 'difficulty'] as const) check(r[key] === request[key], `root mismatch: ${key}`);
  if (r.kind === 'error') {
    check(['input', 'busy', 'initialization', 'execution'].includes(r.code as string) && typeof r.message === 'string' && r.message.length > 0, 'invalid error');
  } else {
    check(r.kind === 'result', 'invalid reply kind');
    parseAiResult(r.result, request);
    const m = object(r.metrics);
    for (const key of ['initMs', 'replayMs', 'searchMs', 'totalMs']) check(typeof m[key] === 'number' && Number.isFinite(m[key]) && m[key] >= 0, 'invalid metrics');
  }
  return r as unknown as SearchReply;
}
