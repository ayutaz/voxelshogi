import { defineConfig, devices } from '@playwright/test';

// Uses the locally installed Google Chrome by default (no browser download);
// CI sets PW_CHANNEL='' to use Playwright's bundled Chromium.
const channel = process.env.PW_CHANNEL ?? 'chrome';
// Set E2E_BASE_URL to run the suite against a deployed site instead of a local preview.
const remoteBaseURL = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: 'e2e',
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: remoteBaseURL ?? 'http://localhost:4173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chrome', use: { ...devices['Desktop Chrome'], ...(channel ? { channel } : {}) } }],
  webServer: remoteBaseURL
    ? undefined
    : {
        command: 'pnpm vite preview --port 4173 --strictPort',
        url: 'http://localhost:4173',
        reuseExistingServer: !process.env.CI,
      },
});
