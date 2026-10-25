import { expect, test } from '@playwright/test';

test('serves the tested build commit', async ({ request }) => {
  const commit = process.env.E2E_COMMIT;
  test.skip(!commit, 'Set E2E_COMMIT to verify the deployed or locally built commit');
  expect(commit).toMatch(/^[0-9a-f]{40}$/);
  const response = await request.get(`/build-info.json?commit=${commit}`);
  expect(response.ok()).toBe(true);
  expect(response.headers()['content-type']).toContain('application/json');
  expect(await response.json()).toEqual({ commit });
});
