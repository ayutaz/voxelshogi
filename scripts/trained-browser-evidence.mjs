import assert from 'node:assert/strict';
export const TRAINED_FIXTURES = ['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b'];
export const TRAINED_PRECISIONS = ['fp32', 'fp16', 'int8'];
const hash = (value, length) => typeof value === 'string' && new RegExp(`^[0-9a-f]{${length}}$`).test(value);
const positive = value => typeof value === 'number' && Number.isFinite(value) && value > 0;
export function requireExternalLinux(platform) { assert.equal(platform, 'linux', 'trained browser measurements require external Linux'); }
export function trainedCases() {
  const cases = [];
  for (const show3D of [false, true]) for (const backend of ['wasm', 'webgpu']) for (const precision of TRAINED_PRECISIONS) for (const fixture of TRAINED_FIXTURES) cases.push({ show3D, backend, precision, fixture });
  return cases;
}
const key = value => JSON.stringify([value.show3D, value.backend, value.precision, value.fixture]);
function placement(validation, backend, precision) {
  assert.equal(validation.information.backend, backend, 'measured backend differs');
  const provider = backend === 'webgpu' ? 'WebGpuExecutionProvider' : 'CPUExecutionProvider';
  assert.deepEqual(Object.keys(validation.profile.providers), [provider], 'unexpected policy provider');
  assert.ok(Number.isSafeInteger(validation.profile.providers[provider]) && validation.profile.providers[provider] > 0, 'missing operator placement');
  assert.ok(Object.keys(validation.profile.operators).length > 0 && Object.values(validation.profile.operators).every(n => Number.isSafeInteger(n) && n > 0), 'operator evidence required');
  if (backend === 'webgpu' && precision === 'fp16') assert.ok(validation.information.features.includes('shader-f16'), 'native FP16 feature required');
  if (backend === 'webgpu') assert.match(validation.information.adapter.vendor, /nvidia/i, 'physical GPU vendor differs');
  else assert.equal(validation.information.adapter, null, 'CPU adapter must be explicit');
  assert.deepEqual(validation.fixtures.map(f => f.name), TRAINED_FIXTURES, 'all same-format references required');
  for (const fixture of validation.fixtures) for (const name of ['policy', 'value']) {
    const stats = fixture.comparison[name];
    const [atol, rtol] = precision === 'fp16' ? [.001, .01] : [name === 'policy' ? .0001 : .00001, .0001];
    assert.equal(stats.atol, atol, 'numeric absolute bound differs');
    assert.equal(stats.rtol, rtol, 'numeric relative bound differs');
    assert.ok([stats.maxAbs, stats.maxRelative].every(n => Number.isFinite(n) && n >= 0), 'invalid numeric difference');
    assert.equal(fixture.comparison[name].elements, name === 'policy' ? 1067985 : 1, 'reference output count differs');
    assert.equal(fixture.comparison[name].exceeded, 0, 'numeric reference comparison failed');
  }
}
function memory(value) {
  assert.ok(value.samples.length >= 2 && value.samples.every(s => positive(s.totalRssBytes)), 'resource observations required');
  assert.ok(Number.isFinite(value.maximumSamplingGapMs) && value.maximumSamplingGapMs >= 0 && value.maximumSamplingGapMs <= 5000, 'resource sampling gap exceeds bound');
}
export function validateTrainedEvidence(report, { allowCandidate = false } = {}) {
  assert.equal(report.schema, 1); assert.equal(report.kind, 'm6-trained-browser-measurement');
  requireExternalLinux(report.platform); assert.equal(report.mode, 'full', 'smoke is not a complete measurement');
  assert.equal(typeof report.candidate, 'boolean');
  assert.ok(allowCandidate || report.candidate === false, 'candidate is not final public proof');
  assert.ok(hash(report.applicationCommit, 40), 'immutable application required');
  assert.match(report.renderer, /nvidia/i, 'physical 3D renderer required');
  assert.doesNotMatch(report.renderer, /swiftshader|llvmpipe/i, 'software renderer is not physical proof');
  const model = report.model;
  assert.equal(model.trained, true, 'trained model required');
  assert.equal(model.numericContract, 'voxelshogi-trained-numeric-v1', 'trained numeric contract differs');
  assert.ok(hash(model.packageHash, 64) && hash(model.sourceCommit, 40) && hash(model.revision, 40), 'model provenance required');
  assert.deepEqual(model.variants.map(v => v.precision), TRAINED_PRECISIONS, 'all formats required');
  assert.ok(model.variants.every(v => hash(v.sha256, 64) && positive(v.bytes)), 'model artifact hashes required');
  assert.deepEqual(report.fixtures.map(f => f.name), TRAINED_FIXTURES, 'fixed positions required');
  const expected = new Set(trainedCases().map(key)), seen = new Set();
  assert.equal(report.rows.length, 48, 'all 48 measurements required');
  let successfulCases = 0, unsupportedCases = 0, gpuSuccess = 0;
  for (const row of report.rows) {
    const id = key(row); assert.ok(expected.has(id) && !seen.has(id), 'missing/duplicate measurement case'); seen.add(id);
    assert.deepEqual(row.selection, { modelId: model.id, packageHash: model.packageHash, precision: row.precision, backend: row.backend }, 'mixed model identity');
    if (row.status === 'unsupported') {
      assert.equal(row.backend, 'webgpu', 'all three CPU formats must be measured');
      assert.equal(row.error.stage, 'initialization', 'runtime failure is not compatibility evidence');
      assert.match(row.error.message, /shader-f16|outputs exceed .* tolerance|not supported|unsupported|WebGPU.*not available/i, 'unclassified error is not unsupported');
      unsupportedCases++; continue;
    }
    assert.equal(row.status, 'done', 'failed measurement');
    placement(row.validation, row.backend, row.precision);
    assert.equal(row.warmupCount, 10, 'ten warmups required');
    assert.equal(row.samples.length, 30, 'thirty measured repetitions required');
    assert.ok([row.cold, ...row.samples].every(s => positive(s.inferenceMs) && positive(s.roundTripMs)), 'invalid measured duration');
    const fixture = report.fixtures.find(f => f.name === row.fixture);
    assert.ok(fixture.legal.some(move => move.move === row.choice.move && move.action === row.choice.action), 'model choice is not Rust-legal');
    assert.ok(Number.isFinite(row.choice.value) && Math.abs(row.choice.value) <= 1, 'invalid model Value');
    memory(row.memory);
    if (row.show3D) {
      assert.ok(row.interaction.draws > 0 && row.interaction.trustedCameraInputs > 0, 'real drawing and trusted input required during repeats');
      assert.ok(Number.isFinite(row.interaction.maximumFrameGapMs) && row.interaction.maximumFrameGapMs <= 5000, 'rendering gap exceeds bound');
    }
    successfulCases++; if (row.backend === 'webgpu') gpuSuccess++;
  }
  assert.equal(seen.size, 48, 'incomplete case matrix');
  assert.ok(gpuSuccess > 0, 'no measured physical GPU model');
  assert.deepEqual(report.switches.map(s => s.backend), ['wasm', 'webgpu'], 'both switch backends required');
  let actualSwitches = 0;
  for (const group of report.switches) {
    assert.ok(TRAINED_PRECISIONS.includes(group.initial));
    assert.equal(group.steps.length, 20, 'twenty actual switches required');
    let previous = group.initial;
    for (const step of group.steps) {
      assert.ok(TRAINED_PRECISIONS.includes(step.precision));
      assert.notEqual(step.precision, previous, 'initial load or repeated model is not a switch');
      assert.equal(step.packageHash, model.packageHash, 'switch model hash differs');
      assert.ok(report.rows.filter(row => row.backend === group.backend && row.precision === step.precision).every(row => row.status === 'done'), 'unsupported format cannot be a successful switch');
      placement(step.validation, group.backend, step.precision); previous = step.precision; actualSwitches++;
    }
    memory(group.memory);
  }
  return { successfulCases, unsupportedCases, actualSwitches };
}
