import { afterEach, expect, it, vi } from 'vitest';
import worker from '../src/collection/worker';
import type { GameDatabase } from '../src/collection/receiver';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const assets = () => ({ fetch: vi.fn().mockResolvedValue(new Response('static shell')) });
it('serves approved model paths before the API 404 and static SPA, without touching games', async () => {
  const fetcher=vi.fn(async()=>new Response('model metadata'));vi.stubGlobal('fetch',fetcher);
  const ASSETS=assets(),GAMES={prepare:vi.fn()} as unknown as GameDatabase;
  const response=await worker.fetch(new Request('https://game.example/api/models/s/6ab524574d36536348dbe323a2b779b9cebe37ed/manifest.json'),{ASSETS,GAMES});
  expect(response.status).toBe(200);expect(await response.text()).toBe('model metadata');
  expect(ASSETS.fetch).not.toHaveBeenCalled();expect(GAMES.prepare).not.toHaveBeenCalled();expect(fetcher).toHaveBeenCalledTimes(1);
});
it('routes /api/games to JSON admission, never the SPA fallback', async () => {
  const ASSETS = assets();
  const response = await worker.fetch(new Request('https://game.example/api/games', { method: 'POST' }), { ASSETS });
  expect(response.status).toBe(503); expect(await response.json()).toEqual({ error: 'collection_unavailable' });
  expect(ASSETS.fetch).not.toHaveBeenCalled();
});
it('describes collection only when enabled and bound, without reading any stored game', async () => {
  const GAMES = { prepare: vi.fn() } as unknown as GameDatabase;
  for (const enabled of ['true', 'false']) {
    const response = await worker.fetch(new Request('https://game.example/api/collection'), { ASSETS: assets(), GAMES, GAME_COLLECTION_ENABLED: enabled });
    expect(await response.json()).toMatchObject({ enabled: enabled === 'true', consent: 'game-research-v1', retentionDays: 30, maxBytes: 262144, privacyPath: '/privacy.html', schemas: [1, 2], policy: 'automatic-game-v2', snapshotIntervalSeconds: 30 });
    expect(response.headers.get('cache-control')).toBe('no-store');
  }
  expect(GAMES.prepare).not.toHaveBeenCalled();
});
it('keeps static assets separate and does not expose a public game listing', async () => {
  const ASSETS = assets();
  expect((await worker.fetch(new Request('https://game.example/api/games/all'), { ASSETS })).status).toBe(404);
  const request = new Request('https://game.example/?models=1');
  expect(await (await worker.fetch(request, { ASSETS })).text()).toBe('static shell');
  expect(ASSETS.fetch).toHaveBeenCalledWith(request);
});
it('purges expired records even with collection OFF and surfaces cleanup failures', async () => {
  vi.spyOn(Date, 'now').mockReturnValue(3000000000000);
  const run = vi.fn().mockResolvedValue({ success: true, meta: {} }), bind = vi.fn().mockReturnValue({ run });
  const prepare = vi.fn().mockReturnValue({ bind });
  const env = { ASSETS: assets(), GAME_COLLECTION_ENABLED: 'false', GAMES: { prepare } as unknown as GameDatabase };
  await worker.scheduled({}, env);
  expect(prepare).toHaveBeenCalledWith('DELETE FROM games WHERE created_at < ?');
  expect(prepare).toHaveBeenCalledWith('DELETE FROM automatic_games WHERE created_at < ?');
  expect(bind).toHaveBeenCalledWith(2997408000);
  run.mockResolvedValue({ success: false, meta: {} });
  await expect(worker.scheduled({}, env)).rejects.toThrow('retention_cleanup_failed');
});
