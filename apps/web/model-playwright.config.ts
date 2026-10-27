import { defineConfig } from '@playwright/test';
import base from './playwright.config';

export default defineConfig(base, {
  testDir: 'model-e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 90_000,
  outputDir: 'model-test-results',
  // Model responses must not enter public trace artifacts before licensing.
  use: { ...base.use, trace: 'off' },
});
