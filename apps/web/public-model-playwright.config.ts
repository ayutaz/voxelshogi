import { defineConfig } from '@playwright/test';
import base from './playwright.config';

export default defineConfig(base, {
  testDir: 'public-model-e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 180_000,
  outputDir: 'public-model-test-results', use: { ...base.use, trace: 'off' },
});
