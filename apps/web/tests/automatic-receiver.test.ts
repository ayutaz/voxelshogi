import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, expect, it } from 'vitest';
import { receiveGame, purgeGames, type GameDatabase } from '../src/collection/receiver';

let db: DatabaseSync;
let GAMES: GameDatabase;
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
function packet(version = 1) {
  return { schema: 2, policy: 'automatic-game-v2', gameId: uuid(1), requestId: uuid(version + 1), version,
    state: 'progress', applicationCommit: 'a'.repeat(40), mode: 'r-r', conditionsScope: 'game-start',
    selectedAgents: { b: { kind: 'easy', seed: 42 }, w: { kind: 'easy', seed: 43 } },
    record: { ruleset_id: 'voxelshogi-standard-v1', initial: '8k/9/9/9/9/9/9/9/K8 b - 1',
      moves: ['191281'], result: null as unknown, termination: null as string | null } };
}
async function send(p: unknown = packet()) {
  return receiveGame(new Request('https://game.example/api/games', { method: 'POST',
    headers: { origin: 'https://game.example', 'content-type': 'application/json' }, body: JSON.stringify(p) }),
  { GAMES, GAME_COLLECTION_ENABLED: 'true' });
}
const row = () => db.prepare('SELECT * FROM automatic_games').get()!;
const usage = () => db.prepare('SELECT * FROM collection_usage').get()!;
beforeEach(() => {
  db = new DatabaseSync(':memory:');
  for (const name of ['0001_games.sql', '0002_automatic_games.sql']) db.exec(readFileSync(new URL(`../migrations/${name}`, import.meta.url), 'utf8'));
  GAMES = { prepare(sql) {
    const statement = db.prepare(sql); let args: (string | number)[] = [];
    const bound = { bind(...values: (string | number)[]) { args = values; return bound; },
      async first<T>() { return (statement.get(...args) ?? null) as T | null; },
      async run() { return { success: true, meta: { changes: Number(statement.run(...args).changes) } }; } };
    return bound;
  } };
});
afterEach(() => db.close());

it('reports creation when D1 counts trigger writes in meta.changes',async()=>{
  const original=GAMES;
  GAMES={prepare(sql){const st=original.prepare(sql);const bound={
    bind(...values:(string|number)[]){st.bind(...values);return bound;},first:<T>()=>st.first<T>(),
    async run(){const result=await st.run();return{...result,meta:{changes:result.meta.changes?5:0}};}
  };return bound;}};
  expect((await send()).status).toBe(201);
  expect(await(await send()).json()).toMatchObject({duplicate:true});
});

it('creates one row, extends it atomically, and never charges duplicate or stale snapshots', async () => {
  const first = packet(); expect((await send(first)).status).toBe(201);
  const next = packet(2); next.record.moves.push('991891');
  const response = await send(next); expect(response.status).toBe(200);
  expect(await response.json()).toMatchObject({ gameId: uuid(1), requestId: uuid(3), version: 2, status: 'received_unverified' });
  const bytes = Number(row().payload_bytes);
  expect(JSON.parse(String(row().payload))).toEqual(next);
  expect(usage()).toMatchObject({ daily_count: 1, retained_bytes: bytes });
  expect((await send(next)).status).toBe(200);
  expect(await (await send(first)).json()).toMatchObject({ version: 2, ignored: true, requestId: first.requestId });
  expect(row()).toMatchObject({ version: 2, progress_writes: 2 });
  expect(db.prepare('SELECT daily_updates FROM automatic_usage').get()!.daily_updates).toBe(2);
});

it('rejects same-version conflicts and branches; preserves the accepted record and accounting', async () => {
  await send(); const bytes = usage().retained_bytes;
  const changed = packet(); changed.record.moves.push('991891');
  expect((await send(changed)).status).toBe(409);
  const branch = packet(2); branch.record.moves = ['991891'];
  expect((await send(branch)).status).toBe(409);
  for (const change of [
    (p: ReturnType<typeof packet>) => { p.applicationCommit = 'b'.repeat(40); },
    (p: ReturnType<typeof packet>) => { p.selectedAgents.b.seed = 9; },
    (p: ReturnType<typeof packet>) => { p.record.initial = '9 b - 1'; },
  ]) { const p = packet(2); change(p); expect((await send(p)).status).toBe(409); }
  expect(row().version).toBe(1); expect(usage().retained_bytes).toBe(bytes);
});

it('keeps terminal snapshots terminal, including delayed progress and concurrent finalization', async () => {
  await send(); const final = packet(2); final.state = 'finished'; final.record.result = { Win: { winner: 'Black', reason: 'Resignation' } }; final.record.termination = 'Resignation';
  expect((await send(final)).status).toBe(200);
  expect((await send(final)).status).toBe(200);
  expect((await send(packet())).status).toBe(200);
  expect((await send(packet(3))).status).toBe(409);
  expect(row()).toMatchObject({ state: 'finished', version: 2 });
  const aborted = packet(3); aborted.state = 'aborted'; aborted.record.termination = 'Abandoned';
  expect((await send(aborted)).status).toBe(409);
});

it.each([
  ['legacy consent', (p: Record<string, unknown>) => { p.consent = true; }],
  ['wrong policy', (p: Record<string, unknown>) => { p.policy = 'game-research-v1'; }],
  ['invalid game id', (p: Record<string, unknown>) => { p.gameId = 'local-file-path'; }],
  ['fractional version', (p: Record<string, unknown>) => { p.version = 1.5; }],
  ['zero version', (p: Record<string, unknown>) => { p.version = 0; }],
  ['empty game', (p: Record<string, unknown>) => { (p.record as { moves: string[] }).moves = []; }],
  ['progress with result', (p: Record<string, unknown>) => { (p.record as { result: unknown }).result = { Draw: { reason: 'MaxPlies' } }; }],
  ['finished without result', (p: Record<string, unknown>) => { p.state = 'finished'; }],
  ['personal metadata', (p: Record<string, unknown>) => { p.email = 'private@example.invalid'; }],
])('rejects %s without persisting', async (_label, change) => {
  const p = packet(); change(p); expect((await send(p)).status).toBe(400);
  expect(db.prepare('SELECT count(*) n FROM automatic_games').get()!.n).toBe(0);
});

it('permits finalization after 128 progress writes, bounds daily writes, and allows retries at every cap', async () => {
  await send();
  for (let version = 2; version <= 128; version++) expect((await send(packet(version))).status).toBe(200);
  expect(row().progress_writes).toBe(128);
  expect((await send(packet(129))).status).toBe(429);
  const final = packet(129); final.state = 'aborted'; final.record.termination = 'Abandoned';
  expect((await send(final)).status).toBe(200);
  db.exec('UPDATE automatic_usage SET daily_updates = 10000');
  expect((await send(final)).status).toBe(200);
  const fresh = packet(); fresh.gameId = uuid(99);
  expect((await send(fresh)).status).toBe(429);
  expect(usage().daily_count).toBe(1);
});

it('shares retained-byte and new-game limits with v1, counts update differences, and expires both tables', async () => {
  await send(); const firstBytes = Number(row().payload_bytes);
  db.exec('UPDATE collection_usage SET retained_bytes = 104857600');
  const longer = packet(2); longer.record.moves.push('991891');
  expect((await send(longer)).status).toBe(429); expect(row().version).toBe(1);
  db.prepare('UPDATE collection_usage SET retained_bytes = ?, daily_count = 1000').run(firstBytes);
  expect((await send(longer)).status).toBe(200);
  const fresh = packet(); fresh.gameId = uuid(99); expect((await send(fresh)).status).toBe(429);
  const created = Number(row().created_at);
  await purgeGames(GAMES, created + 30 * 86400); expect(row()).toBeDefined();
  await purgeGames(GAMES, created + 30 * 86400 + 1);
  expect(db.prepare('SELECT count(*) n FROM automatic_games').get()!.n).toBe(0);
  expect(usage()).toMatchObject({ retained_bytes: 0, daily_count: 1000 });
});

it('rolls daily updates at the UTC day boundary and stores a canonical SHA-256', async () => {
  db.exec("UPDATE automatic_usage SET day = '1970-01-01', daily_updates = 10000");
  expect((await send()).status).toBe(201);
  expect(db.prepare('SELECT daily_updates FROM automatic_usage').get()!.daily_updates).toBe(1);
  const stored = row();
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(String(stored.payload)));
  expect(stored.payload_sha256).toBe([...new Uint8Array(digest)].map(n => n.toString(16).padStart(2, '0')).join(''));
  expect((await send(Object.fromEntries(Object.entries(packet()).reverse()))).status).toBe(200);
});
