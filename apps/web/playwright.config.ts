import { defineConfig, devices } from '@playwright/test';

// Uses the locally installed Google Chrome by default (no browser download);
// CI sets PW_CHANNEL='' to use Playwright's bundled Chromium.
const channel = process.env.PW_CHANNEL ?? 'chrome';

export default defineConfig({
  testDir: 'e2e',
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chrome', use: { ...devices['Desktop Chrome'], ...(channel ? { channel } : {}) } }],
  webServer: {
    command: 'pnpm vite preview --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
  },
});
