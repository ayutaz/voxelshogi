import { COLLECTION_CONSENT, MAX_GAME_BYTES } from './contract';
import { AUTOMATIC_POLICY } from './automatic-contract';
import { purgeGames, receiveGame, type CollectionEnv } from './receiver';
import { publicModelAsset } from './public-model-proxy';

interface Env extends CollectionEnv { ASSETS: { fetch: (request: Request) => Promise<Response> } }
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/models/')) return publicModelAsset(request);
    if (path === '/api/games') return receiveGame(request, env);
    if (path === '/api/collection' && request.method === 'GET') return Response.json({
      enabled: env.GAME_COLLECTION_ENABLED === 'true' && !!env.GAMES,
      consent: COLLECTION_CONSENT, retentionDays: 30, maxBytes: MAX_GAME_BYTES, privacyPath: '/privacy.html',
      schemas: [1, 2], policy: AUTOMATIC_POLICY, snapshotIntervalSeconds: 30,
    }, { headers: { 'cache-control': 'no-store' } });
    if (path.startsWith('/api/')) return Response.json({ error: 'not_found' }, { status: 404 });
    return env.ASSETS.fetch(request);
  },
  async scheduled(_event: unknown, env: Env): Promise<void> {
    // Retention continues even when new collection is disabled.
    if (env.GAMES) {
      const result = await purgeGames(env.GAMES);
      if (!result.success) throw new Error('retention_cleanup_failed');
    }
  },
};
