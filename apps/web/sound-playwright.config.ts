import { defineConfig } from '@playwright/test';
import base from './playwright.config';
export default defineConfig({...base,
  testDir:'sound-e2e',fullyParallel:false,workers:1,retries:0,timeout:60_000,outputDir:'sound-test-results',
  use:{...base.use,trace:'off',screenshot:'only-on-failure'},
  projects:[{name:'chromium',use:{browserName:'chromium'}},{name:'webkit',use:{browserName:'webkit'}}],
});
