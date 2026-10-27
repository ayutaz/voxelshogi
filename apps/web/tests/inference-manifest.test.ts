import { expect, it } from 'vitest';
import { parseDeployment, parseModel } from '../src/inference/manifest';

import { modelFixture, deploymentFixture } from './inference-fixtures';

it('accepts only the supported input/output contract and complete references', () => {
  expect(parseModel(modelFixture()).parameters).toBe(5_021_064);
  expect(parseDeployment(deploymentFixture()).runtime.wasm.parts).toHaveLength(2);
});

for (const kind of ['schema', 'parameters', 'dtype', 'shape', 'empty', 'duplicate', 'missing-reference', 'path', 'license', 'trained']) {
  it(`rejects an invalid model manifest: ${kind}`, () => {
    const m = modelFixture();
    if (kind === 'schema') m.inputSchema = 'other';
    if (kind === 'parameters') m.parameters = 5;
    if (kind === 'dtype') m.inputs.features.dtype = 'float16';
    if (kind === 'shape') m.outputs.policy.shape = [1, 3];
    if (kind === 'empty') m.variants = [];
    if (kind === 'duplicate') m.fixtures.push(m.fixtures[0]!);
    if (kind === 'missing-reference') Reflect.deleteProperty(m.variants[0]!.references, 'initial-b');
    if (kind === 'path') m.variants[0]!.model.path = '../secret';
    if (kind === 'license') m.license = 'unknown';
    if (kind === 'trained') m.trained = true;
    expect(() => parseModel(m)).toThrow();
  });
}

it('rejects runtime version mismatch, missing/reordered-part metadata and unapproved publication', () => {
  const index = deploymentFixture();
  index.runtime.version = 'different';
  expect(() => parseDeployment(index)).toThrow();
  index.runtime.version = '1.31.1'; index.runtime.wasm.bytes = 9;
  expect(() => parseDeployment(index)).toThrow();
  index.runtime.wasm.bytes = 6; index.publication = false;
  expect(() => parseDeployment(index)).toThrow();
  expect(parseDeployment(index, true).publication).toBe(false);
});
