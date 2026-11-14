import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

it.each([undefined, ''])('uses the local preview when E2E_BASE_URL is %j', async value => {
  vi.stubEnv('E2E_BASE_URL', value);
  vi.resetModules();
  const { default: config } = await import('../playwright.config');
  expect(config.use?.baseURL).toBe('http://localhost:4173');
  expect(config.webServer).toMatchObject({ url: 'http://localhost:4173' });
});

it('verifies a deployed site without starting a local preview', async () => {
  vi.stubEnv('E2E_BASE_URL', 'https://voxelshogi.yousan-apps.workers.dev');
  vi.resetModules();
  const { default: config } = await import('../playwright.config');
  expect(config.use?.baseURL).toBe('https://voxelshogi.yousan-apps.workers.dev');
  expect(config.webServer).toBeUndefined();
});
