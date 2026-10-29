import { expect, it } from 'vitest';
import { compare } from '../src/inference/engine';
import { outputTolerances, TRAINED_NUMERIC_CONTRACT } from '../src/inference/numeric';
import { parseModel, parseTrainedModel } from '../src/inference/manifest';
import { modelFixture } from './inference-fixtures';
import { releaseFixture, trainedFixture } from './local-model-fixtures';
const contract = 'voxelshogi-trained-numeric-v1';
it('uses the versioned trained policy bound while retaining M3, Value and FP16 limits', () => {
  expect(TRAINED_NUMERIC_CONTRACT).toBe(contract);
  for (const precision of ['fp32', 'int8'] as const) {
    expect(outputTolerances(precision, 'policy', contract)).toEqual([0.0001, 0.0001]);
    expect(outputTolerances(precision, 'value', contract)).toEqual([0.00001, 0.0001]);
    expect(outputTolerances(precision)).toEqual([0.00001, 0.0001]);
  }
  expect(outputTolerances('fp16', 'policy', contract)).toEqual([0.001, 0.01]);
  expect(outputTolerances('fp16', 'value', contract)).toEqual([0.001, 0.01]);
});
it('checks every trained output without widening an untrained or Value comparison', () => {
  const zero = new Float32Array(2), small = new Float32Array([0.00009, 0]);
  expect(compare(zero, small, 2, 'fp32', contract, 'policy')).toMatchObject({ elements: 2, exceeded: 0, atol: 0.0001, rtol: 0.0001 });
  expect(() => compare(zero, small, 2, 'fp32')).toThrow(/exceed/);
  expect(() => compare(zero, small, 2, 'fp32', contract, 'value')).toThrow(/exceed/);
  expect(() => compare(zero, new Float32Array([0, 0.00011]), 2, 'fp32', contract, 'policy')).toThrow(/1\/2 outputs exceed/);
});
it('requires the known numeric contract on trained packages only', () => {
  const original = trainedFixture(), identity = releaseFixture();
  const good = { ...original, numericContract: contract };
  expect(parseTrainedModel(good, identity).id).toBe(identity.id);
  const missing = { ...good };Reflect.deleteProperty(missing, 'numericContract');
  expect(() => parseTrainedModel(missing, identity)).toThrow(/numeric/);
  expect(() => parseTrainedModel({ ...good, numericContract: 'other' }, identity)).toThrow(/numeric/);
  expect(() => parseModel({ ...modelFixture(), numericContract: contract })).toThrow(/numeric/);
});
it('does not choose permissive limits for unknown numeric contracts or outputs', () => {
  expect(() => outputTolerances('fp32', 'policy', 'other')).toThrow();
  expect(() => outputTolerances('fp32', 'other' as 'policy', contract)).toThrow();
});
