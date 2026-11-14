import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, expect, it } from 'vitest';
import { receiveGame, purgeGames, type GameDatabase } from '../src/collection/receiver';

let db: DatabaseSync;
let binding: GameDatabase;
const id = '00000000-0000-4000-8000-000000000001';
const url = 'https://voxelshogi.example/api/games';
function packet() {
  return { schema: 1, requestId: id, consent: 'game-research-v1', ending: 'aborted', applicationCommit: 'a'.repeat(40),
    mode: 'r-r', conditionsScope: 'selected-at-submission', selectedAgents: { b: { kind: 'easy', seed: 42 }, w: { kind: 'normal', seed: 42, maxDepth: 6, maxNodes: 50000, maxTimeMs: 1000 } },
    record: { ruleset_id: 'voxelshogi-standard-v1', initial: '8k/9/9/9/9/9/9/9/K8 b - 1', moves: ['191281'], result: null, termination: 'Abandoned' } };
}
function post(body: unknown = packet(), headers: Record<string, string> = {}) {
  return new Request(url, { method: 'POST', headers: { origin: new URL(url).origin, 'content-type': 'application/json', ...headers }, body: JSON.stringify(body) });
}
const env = () => ({ GAMES: binding, GAME_COLLECTION_ENABLED: 'true' });
const count = () => (db.prepare('SELECT count(*) AS n FROM games').get() as { n: number }).n;
beforeEach(() => {
  db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('../migrations/0001_games.sql', import.meta.url), 'utf8'));
  db.exec(readFileSync(new URL('../migrations/0002_automatic_games.sql', import.meta.url), 'utf8'));
  binding = { prepare(sql) { let values: (string | number)[] = []; const statement = db.prepare(sql);
    const bound = { bind(...next: (string | number)[]) { values = next; return bound; },
      async first<T>() { return (statement.get(...values) ?? null) as T | null; },
      async run() { const result = statement.run(...values); return { success: true, meta: { changes: Number(result.changes) } }; } };
    return bound;
  } };
});
afterEach(() => db.close());

it('persists one unverified record, re-reads identical JSON, and retries without duplication', async () => {
  const first = await receiveGame(post(), env());
  expect(first.status).toBe(201); expect(count()).toBe(1);
  expect(await first.json()).toMatchObject({ requestId: id, status: 'received_unverified' });
  const row = db.prepare('SELECT payload, payload_sha256, payload_bytes, status FROM games').get() as Record<string, unknown>;
  expect(JSON.parse(String(row.payload))).toEqual(packet());
  expect(row.payload_bytes).toBe(new TextEncoder().encode(JSON.stringify(packet())).length);
  expect(String(row.payload_sha256)).toMatch(/^[0-9a-f]{64}$/);
  const retry = await receiveGame(post(), env());
  expect(retry.status).toBe(200); expect(count()).toBe(1);
  expect(await retry.json()).toMatchObject({ duplicate: true });
});

it('rejects a conflicting retry and preserves the first record', async () => {
  await receiveGame(post(), env());
  const changed = packet(); changed.record.moves.push('991891');
  expect((await receiveGame(post(changed), env())).status).toBe(409);
  expect(count()).toBe(1);
  expect(JSON.parse(String(db.prepare('SELECT payload FROM games').get()!.payload))).toEqual(packet());
});

it('stores only the validated JSON object, excluding hidden overwritten duplicate properties', async () => {
  const body = '{"record":{"private":"must-not-be-retained"},' + JSON.stringify(packet()).slice(1);
  const request = new Request(url, { method: 'POST', headers: { origin: new URL(url).origin, 'content-type': 'application/json' }, body });
  expect((await receiveGame(request, env())).status).toBe(201);
  expect(String(db.prepare('SELECT payload FROM games').get()!.payload)).not.toContain('must-not-be-retained');
});

it('keeps concurrent submissions within the daily quota', async () => {
  db.exec('UPDATE collection_usage SET daily_count = 999');
  const second = { ...packet(), requestId: '00000000-0000-4000-8000-000000000002' };
  const responses = await Promise.all([receiveGame(post(), env()), receiveGame(post(second), env())]);
  expect(responses.map(response => response.status).sort()).toEqual([201, 429]);
  expect(count()).toBe(1);
  expect(db.prepare('SELECT daily_count FROM collection_usage').get()!.daily_count).toBe(1000);
});

it.each([
  ['consent missing', (p: Record<string, unknown>) => { delete p.consent; }],
  ['consent false', (p: Record<string, unknown>) => { p.consent = false; }],
  ['unexpected personal field', (p: Record<string, unknown>) => { p.email = 'someone@example.invalid'; }],
  ['invalid commit', (p: Record<string, unknown>) => { p.applicationCommit = 'main'; }],
  ['multiplayer mode', (p: Record<string, unknown>) => { p.mode = 'h-h'; }],
  ['malformed move', (p: Record<string, unknown>) => { (p.record as { moves: unknown[] }).moves = [123]; }],
  ['too many moves', (p: Record<string, unknown>) => { (p.record as { moves: string[] }).moves = Array(2049).fill('191281'); }],
  ['unsupported rules', (p: Record<string, unknown>) => { (p.record as { ruleset_id: string }).ruleset_id = 'nine-kings'; }],
  ['arbitrary record metadata', (p: Record<string, unknown>) => { (p.record as Record<string, unknown>).token = 'private'; }],
  ['unfinished labelled finished', (p: Record<string, unknown>) => { p.ending = 'finished'; }],
  ['arbitrary agent metadata', (p: Record<string, unknown>) => { ((p.selectedAgents as Record<string, Record<string, unknown>>).b!).path = '/private/model'; }],
])('rejects %s without storing anything', async (_name, change) => {
  const value = packet(); change(value);
  expect((await receiveGame(post(value), env())).status).toBe(400); expect(count()).toBe(0);
});

it('accepts a structurally valid finished record without claiming the outcome is verified', async () => {
  const value = { ...packet(), ending: 'finished', record: { ...packet().record, result: { Win: { winner: 'Black', reason: 'Resignation' } }, termination: 'Resignation' } };
  expect((await receiveGame(post(value), env())).status).toBe(201);
  expect(db.prepare('SELECT status FROM games').get()!.status).toBe('received_unverified');
});

it('fails closed when disabled, foreign-origin, wrong-method, or wrong media type', async () => {
  expect((await receiveGame(post(), { ...env(), GAME_COLLECTION_ENABLED: 'false' })).status).toBe(503);
  expect((await receiveGame(post(undefined, { origin: 'https://foreign.invalid' }), env())).status).toBe(403);
  expect((await receiveGame(new Request(url), env())).status).toBe(405);
  expect((await receiveGame(post(undefined, { 'content-type': 'text/plain' }), env())).status).toBe(415);
  expect(count()).toBe(0);
});

it('bounds actual streamed bytes even without a Content-Length header', async () => {
  expect((await receiveGame(post('x'.repeat(256 * 1024)), env())).status).toBe(413);
  expect((await receiveGame(post('あ'.repeat(90000)), env())).status).toBe(413);
  expect(count()).toBe(0);
});

it('resets only the daily counter at a UTC day boundary', async () => {
  db.exec("UPDATE collection_usage SET day = '1970-01-01', daily_count = 1000");
  expect((await receiveGame(post(), env())).status).toBe(201);
  expect(db.prepare('SELECT daily_count FROM collection_usage').get()!.daily_count).toBe(1);
});

it('canonicalizes formatting and property order for idempotent retries', async () => {
  expect((await receiveGame(post(), env())).status).toBe(201);
  const reordered = Object.fromEntries(Object.entries(packet()).reverse());
  expect((await receiveGame(post(reordered), env())).status).toBe(200); expect(count()).toBe(1);
});

it('enforces the atomic daily quota, but permits an identical retry at the cap', async () => {
  await receiveGame(post(), env());
  db.exec('UPDATE collection_usage SET daily_count = 1000');
  expect((await receiveGame(post(), env())).status).toBe(200);
  const next = packet(); next.requestId = '00000000-0000-4000-8000-000000000002';
  expect((await receiveGame(post(next), env())).status).toBe(429); expect(count()).toBe(1);
});

it('limits retained bytes independently of daily requests and rolls back counters on rejection', async () => {
  db.exec('UPDATE collection_usage SET retained_bytes = 104857600');
  expect((await receiveGame(post(), env())).status).toBe(429); expect(count()).toBe(0);
  expect(db.prepare('SELECT daily_count FROM collection_usage').get()!.daily_count).toBe(0);
});

it('deletes only expired records and releases their retained-byte accounting', async () => {
  await receiveGame(post(), env());
  const old = Number(db.prepare('SELECT created_at FROM games').get()!.created_at);
  await purgeGames(binding, old + 30 * 86400);
  expect(count()).toBe(1);
  await purgeGames(binding, old + 30 * 86400 + 1);
  expect(count()).toBe(0);
  expect(db.prepare('SELECT retained_bytes, daily_count FROM collection_usage').get()).toMatchObject({ retained_bytes: 0, daily_count: 1 });
});

it('never exposes SQL details or payloads on database failure', async () => {
  const broken = { prepare() { throw new Error('sensitive SQL query details'); } } as GameDatabase;
  const response = await receiveGame(post(), { ...env(), GAMES: broken });
  expect(response.status).toBe(503); expect(await response.text()).not.toContain('sensitive');
});
