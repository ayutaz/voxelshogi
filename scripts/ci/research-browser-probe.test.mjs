import assert from 'node:assert/strict';
import test from 'node:test';
import { compareVector, readResearch, researchBrowserCases, requireLinux, validateBrowserInputs, validateProvider } from '../research-browser-contract.mjs';

const file = (path, bytes) => ({ path, bytes, sha256: 'a'.repeat(64) });
export function inputs() {
  return { schema: 'voxelshogi-research-browser-input-v1', trained: false,
    model_source_commit: 'b'.repeat(40), release_sha256: 'c'.repeat(64),
    origin: { repo_id: 'voxelshogi/voxelshogi-research-operator-probe-v1', revision: 'd'.repeat(40) },
    numeric: { policy_atol: 1e-4, policy_rtol: 1e-4, value_atol: 1e-5, value_rtol: 1e-5 },
    warmup_steps: 8, measured_steps: 32,
    models: ['full', 'axial', 'geometry', 'cnn'].map(name => ({ name, parameters: 28_000_000, model: file(`${name}/fp32.onnx`, 108_000_000),
      fixtures: [0, 3].map(id => ({ id, features: file(`${name}/fixture${id}.features.f32`, 125388), policy: file(`${name}/fixture${id}.policy.f32`, 4271940), value: file(`${name}/fixture${id}.value.f32`, 4), legal_actions: [0, 1] })) })) };
}
test('exact four structures and both backends are enumerated without dropping fixtures', () => {
  assert.doesNotThrow(() => validateBrowserInputs(inputs()));
  const cases = researchBrowserCases();
  assert.equal(cases.length, 8);
  assert.deepEqual(cases[0], { name: 'full', backend: 'wasm' });
  assert.deepEqual(cases.at(-1), { name: 'cnn', backend: 'webgpu' });
});
test('M file sizes are accepted in the research contract without weakening legacy manifests', () => {
  const value = inputs(); value.models[2].model.bytes = 138883036;
  assert.doesNotThrow(() => validateBrowserInputs(value));
  for (const change of [v => v.models.pop(), v => v.models[1].name = 'full', v => v.models[0].fixtures.pop(), v => v.trained = true, v => v.models[0].parameters = 5_021_064, v => v.models[0].model.path = '../model.onnx', v => v.models[0].fixtures[0].features.bytes = 125384, v => v.numeric.value_rtol = 1e-4, v => v.measured_steps = 1, v => v.origin.revision = 'main']) {
    const bad = inputs();change(bad);assert.throws(() => validateBrowserInputs(bad));
  }
});
test('full-vector comparison uses hand-calculated mixed absolute and relative limits', () => {
  const expected = new Float32Array([1, 2, 0, -1]);
  const actual = new Float32Array([1.125, 2.25, 0.25, -1]);
  // atol=.125, rtol=.0625 => bounds .1875,.25,.125,.1875.
  assert.deepEqual(compareVector(expected, actual, 4, .125, .0625), { elements: 4, exceeded: 1, max_abs: .25 });
  assert.throws(() => compareVector(expected, actual.subarray(1), 4, .125, .0625));
  assert.throws(() => compareVector(expected, new Float32Array([1, 2, NaN, -1]), 4, .125, .0625));
  assert.throws(() => compareVector(new Float32Array([Infinity]), new Float32Array([1]), 1, .125, .0625));
});
test('the real runner refuses the editing Mac', () => {
  requireLinux('linux');assert.throws(() => requireLinux('darwin'));assert.throws(() => requireLinux('win32'));
});
test('research download verifies exact bytes and rejects corrupt or oversized bodies', async () => {
  const descriptor = { path: 'fixture.bin', bytes: 3, sha256: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' };
  const fetcher = body => async () => new Response(body);
  assert.deepEqual([...await readResearch('http://127.0.0.1/fixture.bin', descriptor, fetcher('abc'))], [97, 98, 99]);
  await assert.rejects(() => readResearch('http://127.0.0.1/fixture.bin', descriptor, fetcher('abd')), /hash/);
  await assert.rejects(() => readResearch('http://127.0.0.1/fixture.bin', descriptor, fetcher('abcd')), /size/);
});
test('backend placement requires actual operator profile and hardware identity', () => {
  const row = { backend: 'webgpu', information: { backend: 'webgpu', adapter: { vendor: 'NVIDIA', architecture: 'blackwell' } }, profile: { providers: { WebGpuExecutionProvider: 5 }, operators: { MatMul: 5 } } };
  validateProvider(row);
  for (const change of [v => v.profile.providers.CPUExecutionProvider = 1, v => v.profile.operators = {}, v => v.information.adapter.vendor = 'SwiftShader', v => v.information.adapter = null]) {
    const bad = structuredClone(row);change(bad);assert.throws(() => validateProvider(bad));
  }
  validateProvider({ backend: 'wasm', information: { backend: 'wasm', adapter: null }, profile: { providers: { CPUExecutionProvider: 2 }, operators: { MatMul: 2 } } });
});
