import { afterEach, beforeEach, expect, it, vi, type Mock } from 'vitest';
import { AutomaticCollection } from '../src/collection/automatic-client';

const conditions = { mode: 'r-r' as const, selectedAgents: { b: { kind: 'easy' as const, seed: 42 }, w: { kind: 'easy' as const, seed: 43 } } };
const record = (moves = ['191281'], terminal = false) => JSON.stringify({ ruleset_id: 'voxelshogi-standard-v1', initial: '8k/9/K8 b - 1', moves,
  result: terminal ? { Win: { winner: 'Black', reason: 'Resignation' } } : null, termination: terminal ? 'Resignation' : null });
let client: AutomaticCollection;
let posts: { body: string; options: RequestInit }[];
let fetcher: Mock<typeof fetch>;
beforeEach(() => {
  vi.useFakeTimers(); posts = [];
  fetcher = vi.fn<typeof fetch>(async (input, options) => {
    const url = String(input);
    if (url === '/build-info.json') return Response.json({ commit: 'a'.repeat(40) });
    if (url === '/api/collection') return Response.json({ enabled: true, policy: 'automatic-game-v2', schemas: [1, 2] });
    posts.push({ body: String(options?.body), options: options! });
    const p = JSON.parse(String(options?.body));
    return Response.json({ gameId: p.gameId, requestId: p.requestId, version: p.version, status: 'received_unverified' });
  });
});
afterEach(() => { client?.dispose(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const tick = () => vi.advanceTimersByTimeAsync(0);
const packet = (i: number) => JSON.parse(posts[i]!.body);

it('saves the first real move, coalesces changes for 30 seconds, and ignores cursor-only updates', async () => {
  client = new AutomaticCollection(fetcher); await client.ready;
  client.observe(record([]), conditions); await tick(); expect(posts).toHaveLength(0);
  client.observe(record(), conditions); await tick(); expect(posts).toHaveLength(1);
  expect(packet(0)).toMatchObject({ schema: 2, policy: 'automatic-game-v2', version: 1, state: 'progress', conditionsScope: 'game-start', selectedAgents: conditions.selectedAgents });
  expect(packet(0)).not.toHaveProperty('consent');
  client.observe(record(), conditions); await tick(); expect(posts).toHaveLength(1);
  client.observe(record(['191281', '991891']), conditions);
  await vi.advanceTimersByTimeAsync(29999); expect(posts).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1); expect(posts).toHaveLength(2);
  expect(packet(1)).toMatchObject({ gameId: packet(0).gameId, version: 2, record: { moves: ['191281', '991891'] } });
  client.flush(); await tick(); expect(posts).toHaveLength(2);
});

it('freezes start conditions and saves final results once, independent of the history cursor', async () => {
  client = new AutomaticCollection(fetcher); await client.ready;
  client.observe(record(), conditions); await tick();
  const changed = structuredClone(conditions); changed.selectedAgents.b.seed = 999;
  client.observe(record(['191281', '991891'], true), changed); await tick();
  expect(posts).toHaveLength(2); expect(packet(1)).toMatchObject({ state: 'finished', selectedAgents: conditions.selectedAgents });
  client.observe(record(['191281', '991891'], true), changed); client.flush(); await tick();
  expect(posts).toHaveLength(2);
});

it('closes replaced games with their own ID, starts a new ID, and never sends imported games or their branches', async () => {
  client = new AutomaticCollection(fetcher); await client.ready;
  client.observe(record(), conditions); await tick(); const firstId = client.gameId;
  client.begin(false); await tick();
  expect(packet(1)).toMatchObject({ gameId: firstId, state: 'aborted', record: { result: null, termination: 'Abandoned' } });
  client.observe(record(['991891'], true), conditions); client.flush(); await tick(); expect(posts).toHaveLength(2);
  client.begin(false); client.observe(record(), conditions); await tick(); expect(posts).toHaveLength(2);
  client.begin(true); client.observe(record(), conditions); await tick();
  expect(posts).toHaveLength(3); expect(packet(2).gameId).not.toBe(firstId);
});

it('retries one immutable request only at 2/8/30 seconds, then continues later games', async () => {
  client = new AutomaticCollection(fetcher); await client.ready;
  fetcher.mockImplementation(async (_url, options) => {
    if (!options) throw new Error('expected POST');
    posts.push({ body: String(options.body), options }); return Response.json({ error: 'unavailable' }, { status: 503 });
  });
  client.observe(record(), conditions); await tick(); expect(posts).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1999); expect(posts).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1); expect(posts).toHaveLength(2);
  await vi.advanceTimersByTimeAsync(8000); expect(posts).toHaveLength(3);
  await vi.advanceTimersByTimeAsync(30000); expect(posts).toHaveLength(4);
  await vi.advanceTimersByTimeAsync(120000); expect(posts).toHaveLength(4);
  expect(new Set(posts.map(p => p.body)).size).toBe(1);
  client.begin(true); client.observe(record(), conditions); await tick(); expect(posts).toHaveLength(5);
});

it('coalesces the newest pending snapshot while one request is in flight and validates acknowledgements', async () => {
  client = new AutomaticCollection(fetcher); await client.ready;
  let finish!: (response: Response) => void;
  fetcher.mockImplementationOnce((_url, options) => {
    if (!options) throw new Error('expected POST');
    posts.push({ body: String(options.body), options }); return new Promise<Response>(resolve => { finish = resolve; });
  });
  client.observe(record(), conditions); await tick();
  client.observe(record(['191281', '991891']), conditions); client.flush();
  client.observe(record(['191281', '991891', '281371']), conditions); client.flush();
  expect(posts).toHaveLength(1);
  finish(Response.json({ gameId: 'wrong', requestId: packet(0).requestId, version: 1, status: 'received_unverified' })); await tick();
  await vi.advanceTimersByTimeAsync(2000);
  expect(posts).toHaveLength(3); expect(posts[1]!.body).toBe(posts[0]!.body);
  expect(packet(2).record.moves).toEqual(['191281', '991891', '281371']);
});

it('keeps the replaced game separate while build metadata is still loading', async () => {
  let resolveBuild!: (response: Response) => void;
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((url, options) => String(url) === '/build-info.json'
    ? new Promise<Response>(resolve => { resolveBuild = resolve; }) : original(url, options));
  client = new AutomaticCollection(fetcher);
  client.observe(record(), conditions); const oldId = client.gameId;
  client.begin(true); client.observe(record(['991891']), conditions);
  resolveBuild(Response.json({ commit: 'a'.repeat(40) })); await client.ready; await tick();
  expect(posts).toHaveLength(2);
  expect(packet(0)).toMatchObject({ gameId: oldId, state: 'aborted', record: { moves: ['191281'] } });
  expect(packet(1)).toMatchObject({ gameId: client.gameId, state: 'progress', record: { moves: ['991891'] } });
});
it('recovers a transient metadata failure and saves the first move already played', async () => {
  fetcher.mockRejectedValueOnce(new Error('offline'));
  client = new AutomaticCollection(fetcher); client.observe(record(),conditions);
  await tick();expect(posts).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(1999);expect(posts).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(1);await client.ready;
  expect(posts).toHaveLength(1);expect(packet(0).record.moves).toEqual(['191281']);
});
it('does not save a copied branch prefix before its first new real move', async () => {
  client = new AutomaticCollection(fetcher);await client.ready;
  client.begin(true,1);client.observe(record(),conditions);client.flush();await tick();expect(posts).toHaveLength(0);
  client.observe(record(['191281','991891']),conditions);await tick();expect(posts).toHaveLength(1);
});

it('binds native fetch, omits credentials, and keeps unavailable metadata or invalid payloads silent', async () => {
  vi.stubGlobal('fetch', function(this: unknown, url: string, options?: RequestInit) {
    expect(this).toBe(globalThis); return fetcher(url, options);
  });
  client = new AutomaticCollection(); await client.ready;
  client.observe(record(), conditions); await tick();
  expect(posts[0]!.options).toMatchObject({ credentials: 'omit', redirect: 'error', cache: 'no-store' });
  client.begin(true); client.observe('invalid', conditions); client.observe(record(Array(2049).fill('191281')), conditions); await tick();
  expect(posts).toHaveLength(2); // replacement finalization only
  client.dispose(); fetcher.mockImplementation(async () => Response.json({ enabled: false }));
  client = new AutomaticCollection(fetcher); await client.ready; client.observe(record(), conditions); await tick();
  expect(posts).toHaveLength(2);
});
