import { isGameSubmission, MAX_GAME_BYTES } from './contract';
import { isAutomaticSubmission } from './automatic-contract';
import { persistAutomatic } from './automatic-receiver';

export interface GameStatement {
  bind: (...values: (string | number)[]) => GameStatement;
  first: <T>() => Promise<T | null>;
  run: () => Promise<{ success: boolean; meta: { changes?: number } }>;
}
export interface GameDatabase { prepare: (sql: string) => GameStatement }
export interface CollectionEnv { GAMES?: GameDatabase; GAME_COLLECTION_ENABLED?: string }

function json(body: unknown, status: number): Response {
  return Response.json(body, { status, headers: { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' } });
}
function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
async function boundedBody(request: Request): Promise<string> {
  const reader = request.body?.getReader();
  if (!reader) return '';
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let size = 0, text = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_GAME_BYTES) { await reader.cancel(); throw new RangeError('oversized'); }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } finally { reader.releaseLock(); }
}

export async function receiveGame(request: Request, env: CollectionEnv): Promise<Response> {
  if (request.method !== 'POST') return json({ error: 'method_not_allowed' }, 405);
  if (env.GAME_COLLECTION_ENABLED !== 'true' || !env.GAMES) return json({ error: 'collection_unavailable' }, 503);
  if (request.headers.get('origin') !== new URL(request.url).origin) return json({ error: 'origin_rejected' }, 403);
  if (request.headers.get('content-type')?.split(';')[0]?.trim().toLowerCase() !== 'application/json') return json({ error: 'json_required' }, 415);
  const declared = request.headers.get('content-length');
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_GAME_BYTES)) return json({ error: 'payload_too_large' }, 413);
  let body: string, value: unknown;
  try { body = await boundedBody(request); value = JSON.parse(body); }
  catch (error) { return json({ error: error instanceof RangeError ? 'payload_too_large' : 'invalid_json' }, error instanceof RangeError ? 413 : 400); }
  if (!isGameSubmission(value) && !isAutomaticSubmission(value)) return json({ error: 'invalid_submission' }, 400);
  // Do not retain raw JSON properties hidden by duplicate keys during parsing.
  body = canonicalJson(value);
  const bytes = new TextEncoder().encode(body);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const sha = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  try {
    if (value.schema === 2) {
      const saved = await persistAutomatic(env.GAMES, value, body, sha, bytes.byteLength);
      return json(saved.body, saved.status);
    }
    const inserted = await env.GAMES.prepare('INSERT INTO games(request_id, payload_sha256, payload, payload_bytes) VALUES (?, ?, ?, ?) ON CONFLICT(request_id) DO NOTHING')
      .bind(value.requestId, sha, body, bytes.byteLength).run();
    if (!inserted.success) throw new Error('write failed');
    const row = await env.GAMES.prepare('SELECT payload_sha256, status FROM games WHERE request_id = ?').bind(value.requestId).first<{ payload_sha256: string; status: string }>();
    if (!row) throw new Error('read failed');
    if (row.payload_sha256 !== sha) return json({ error: 'request_id_conflict' }, 409);
    const duplicate = inserted.meta.changes === 0;
    return json({ requestId: value.requestId, status: row.status, duplicate }, duplicate ? 200 : 201);
  } catch (error) {
    // Return a stable code; never log the request, SQL bindings, IP, or exception.
    const quota = error instanceof Error && error.message.includes('collection_quota');
    if (error instanceof Error && error.message.includes('collection_conflict')) return json({ error: 'snapshot_conflict' }, 409);
    return json({ error: quota ? 'collection_limit' : 'collection_unavailable' }, quota ? 429 : 503);
  }
}

export async function purgeGames(db: GameDatabase, nowSeconds = Math.floor(Date.now() / 1000)) {
  const cutoff = nowSeconds - 30 * 86400;
  const legacy = await db.prepare('DELETE FROM games WHERE created_at < ?').bind(cutoff).run();
  const automatic = await db.prepare('DELETE FROM automatic_games WHERE created_at < ?').bind(cutoff).run();
  return { success: legacy.success && automatic.success, meta: {} };
}
