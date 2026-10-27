import assert from 'node:assert/strict';
import test from 'node:test';
import { modelSwitchVariants } from '../measure-browser-models.mjs';

test('twenty model switches all change the preceding model, excluding the initial load', () => {
  const variants = modelSwitchVariants(20);
  assert.equal(variants.length, 20);
  assert.deepEqual(new Set(variants), new Set(['fp32', 'fp16', 'int8']));
  let previous = 'fp32';
  for (const variant of variants) { assert.notEqual(variant, previous); previous = variant; }
  assert.deepEqual(modelSwitchVariants(2), ['fp16', 'int8']);
});
