import assert from 'node:assert/strict';
import test from 'node:test';
import { trainedCases, validateTrainedEvidence, requireExternalLinux } from '../trained-browser-evidence.mjs';
// Opaque metadata fixtures only. These tests never execute a model or browser.
const fixtures = ['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b'];
const precisions = ['fp32', 'fp16', 'int8'];
const profile = backend => ({ information: { backend, adapter: backend === 'webgpu' ? { vendor: 'nvidia', architecture: 'blackwell' } : null, features: backend === 'webgpu' ? ['shader-f16'] : [] }, profile: { providers: { [backend === 'webgpu' ? 'WebGpuExecutionProvider' : 'CPUExecutionProvider']: 8 }, operators: { MatMul: 8 } }, fixtures: fixtures.map(name => ({ name, comparison: { policy: { elements: 1067985, exceeded: 0 }, value: { elements: 1, exceeded: 0 } } })) });
export function evidence() {
  const model = { id: 'voxelshogi-transformer-s-m6-314159-v1', trained: true, packageHash: 'a'.repeat(64), sourceCommit: 'b'.repeat(40), revision: 'c'.repeat(40), variants: precisions.map((precision, index) => ({ precision, sha256: String(index + 1).repeat(64), bytes: 100 })) };
  const rows = [];
  for (const show3D of [false, true]) for (const backend of ['wasm', 'webgpu']) for (const precision of precisions) for (const fixture of fixtures) rows.push({ show3D, backend, precision, fixture, status: 'done', selection: { modelId: model.id, packageHash: model.packageHash, precision, backend }, validation: profile(backend), cold: { inferenceMs: 3, roundTripMs: 4 }, warmupCount: 10, samples: Array.from({ length: 30 }, () => ({ inferenceMs: 3, roundTripMs: 4 })), choice: { move: '111112', action: 2, value: .25 }, memory: { samples: [{ totalRssBytes: 1000 }, { totalRssBytes: 1200 }], maximumSamplingGapMs: 1000 }, interaction: { draws: show3D ? 5 : 0, trustedCameraInputs: show3D ? 3 : 0, maximumFrameGapMs: 30 } });
  const switches = ['wasm', 'webgpu'].map(backend => ({ backend, initial: 'fp32', steps: Array.from({ length: 20 }, (_, i) => ({ precision: i % 2 === 0 ? 'int8' : 'fp32', packageHash: model.packageHash, validation: profile(backend) })), memory: { samples: [{ totalRssBytes: 1000 }, { totalRssBytes: 1200 }], maximumSamplingGapMs: 1000 } }));
  return { schema: 1, kind: 'm6-trained-browser-measurement', mode: 'full', candidate: false, platform: 'linux', applicationCommit: 'd'.repeat(40), renderer: 'ANGLE (NVIDIA, RTX 5090)', model, fixtures: fixtures.map(name => ({ name, legal: [{ move: '111112', action: 2 }] })), rows, switches };
}
test('the measurement matrix contains exactly the 48 predeclared cases', () => {
  const cases = trainedCases(); assert.equal(cases.length, 48);
  assert.deepEqual(cases[0], { show3D: false, backend: 'wasm', precision: 'fp32', fixture: 'initial-b' });
  assert.deepEqual(cases.at(-1), { show3D: true, backend: 'webgpu', precision: 'int8', fixture: 'material-b' });
  assert.equal(new Set(cases.map(c => JSON.stringify(c))).size, 48);
});
test('complete evidence requires all measured cases and twenty actual switches per backend', () => {
  assert.deepEqual(validateTrainedEvidence(evidence()), { successfulCases: 48, unsupportedCases: 0, actualSwitches: 40 });
  for (const change of [x => x.rows.pop(), x => x.rows[1] = structuredClone(x.rows[0]), x => x.rows[0].samples.pop(), x => x.rows[0].warmupCount = 0, x => x.switches[0].steps.pop(), x => x.switches[0].steps[0].precision = 'fp32']) {
    const value = evidence(); change(value); assert.throws(() => validateTrainedEvidence(value));
  }
});
test('software fallback, incomplete references and mixed model identity cannot pass', () => {
  for (const change of [x => x.renderer = 'SwiftShader', x => x.rows[12].validation.profile.providers = { CPUExecutionProvider: 8 }, x => x.rows[12].validation.profile.providers = { WebGpuExecutionProvider: 8, CPUExecutionProvider: 1 }, x => x.rows[0].validation.profile.operators = {}, x => x.rows[0].validation.fixtures.pop(), x => x.rows[0].validation.fixtures[0].comparison.policy.exceeded = 1, x => x.rows[0].selection.packageHash = 'e'.repeat(64), x => x.rows[0].choice.move = '999998', x => x.model.trained = false]) {
    const value = evidence(); change(value); assert.throws(() => validateTrainedEvidence(value));
  }
});
test('an explicit GPU FP16 numeric rejection is preserved without labelling missing CPU results unsupported', () => {
  const value = evidence();for (const row of value.rows) if (row.backend === 'webgpu' && row.precision === 'fp16') { row.status = 'unsupported'; row.error = { stage: 'initialization', message: '3/1067985 outputs exceed fp16 tolerance' }; }
  assert.deepEqual(validateTrainedEvidence(value), { successfulCases: 40, unsupportedCases: 8, actualSwitches: 40 });
  const contradictory = structuredClone(value); contradictory.switches[1].steps[0].precision = 'fp16'; assert.throws(() => validateTrainedEvidence(contradictory));
  value.rows[0].status = 'unsupported';value.rows[0].error = { stage: 'initialization', message: 'unsupported' };assert.throws(() => validateTrainedEvidence(value));
  const network = evidence();for (const row of network.rows) if (row.backend === 'webgpu' && row.precision === 'fp16') { row.status = 'unsupported';row.error = { stage: 'initialization', message: 'download failed:404' }; } assert.throws(() => validateTrainedEvidence(network));
});
test('missing physical interaction or unobserved resource intervals cannot count as complete', () => {
  for (const change of [x => x.rows[24].interaction.draws = 0, x => x.rows[24].interaction.trustedCameraInputs = 0, x => x.rows[0].memory.samples = [], x => x.rows[0].memory.maximumSamplingGapMs = 5001, x => x.rows[24].interaction.maximumFrameGapMs = 5001]) {
    const value = evidence();change(value);assert.throws(() => validateTrainedEvidence(value));
  }
});
test('candidate, smoke and non-Linux runs do not become final public proof', () => {
  const value = evidence();value.candidate = true;assert.throws(() => validateTrainedEvidence(value));
  assert.equal(validateTrainedEvidence(value, { allowCandidate: true }).successfulCases, 48);
  value.mode = 'smoke';assert.throws(() => validateTrainedEvidence(value, { allowCandidate: true }));
  requireExternalLinux('linux');assert.throws(() => requireExternalLinux('darwin'));assert.throws(() => requireExternalLinux('win32'));
});
