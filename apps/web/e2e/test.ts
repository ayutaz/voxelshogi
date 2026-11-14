import { test as base, expect } from '@playwright/test';

/** UI suites never leave synthetic games in production D1. Dedicated HTTP/D1 proof is separate. */
export const test = base.extend({
  page: async ({ page }, runTest) => {
    await page.route('**/api/collection', route => route.fulfill({ json: { enabled: true, policy: 'automatic-game-v2', schemas: [1,2] } }));
    await page.route('**/api/games', route => {
      const p = route.request().postDataJSON();
      return route.fulfill({ json: { gameId: p.gameId, requestId: p.requestId, version: p.version, status: 'received_unverified' } });
    });
    await runTest(page);
  },
});
export { expect };
