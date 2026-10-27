import { expect, it } from 'vitest';
import { inferenceOptions } from '../src/inference/options';

it('keeps weight-only INT8 dequantization semantics and prevents silent GPU fallback', () => {
  expect(inferenceOptions('wasm', 'int8').graphOptimizationLevel).toBe('basic');
  expect(inferenceOptions('webgpu', 'int8').graphOptimizationLevel).toBe('basic');
  expect(inferenceOptions('wasm', 'fp32').graphOptimizationLevel).toBe('all');
  expect(inferenceOptions('webgpu', 'fp16').graphOptimizationLevel).toBe('all');
  expect(inferenceOptions('webgpu', 'int8').extra).toEqual({ session: { disable_cpu_ep_fallback: '1' } });
});
