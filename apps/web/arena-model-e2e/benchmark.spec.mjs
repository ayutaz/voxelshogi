import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { measureTrainedModels } from '../../../scripts/measure-trained-models.mjs';

test('the actual measurement driver loads local ONNX, repeats requests and replaces Worker formats', async ({ browser, baseURL }) => {
  const fixture=resolve(process.env.M6_MODEL_FIXTURE ?? '../../runs/m6/browser-fixture');
  const report=await measureTrainedModels({browser,base:baseURL,modelFolder:resolve(fixture,'model'),catalog:JSON.parse(readFileSync(resolve(fixture,'catalog.json'),'utf8')),output:resolve(fixture,'benchmark-smoke.json'),candidate:true,smoke:true});
  expect(report.complete).toBe(true);expect(report.mode).toBe('smoke');expect(report.candidate).toBe(true);
  expect(report.rows).toHaveLength(1);expect(report.rows[0].warmupCount).toBe(10);expect(report.rows[0].samples).toHaveLength(1);
  expect(report.rows[0].validation.fixtures).toHaveLength(4);expect(report.switches[0].steps.map(s=>s.precision)).toEqual(['fp16','fp32']);
  expect(report.rows[0].memory.samples.length).toBeGreaterThanOrEqual(2);
});
