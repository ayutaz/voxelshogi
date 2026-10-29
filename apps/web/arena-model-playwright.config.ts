import { defineConfig } from '@playwright/test';
import base from './playwright.config';

export default defineConfig(base, {
  testDir: 'arena-model-e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 120_000,
  outputDir: 'arena-model-test-results', use: { ...base.use, trace: 'off' },
});
