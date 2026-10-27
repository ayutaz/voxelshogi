// Lifecycle/control tests use fake sessions; actual GPU evidence comes from real Chrome.
import { expect, it, vi } from 'vitest';
import { InferenceEngine } from '../src/inference/engine';
import { parseDeployment, parseModel, POLICY_ELEMENTS } from '../src/inference/manifest';
import { modelFixture, deploymentFixture } from './inference-fixtures';

const expectedPolicy = new Float32Array(POLICY_ELEMENTS).fill(0.25), expectedValue = new Float32Array([-0.5]);
const request = () => ({ schema: 1, kind: 'infer', requestId: 1, revision: 2, packageHash: 'a'.repeat(64), variant: 'fp32', fixture: 'initial-b', backend: 'wasm', iterations: 1 } as const);
function setup() {
  const released = vi.fn(), disposed = vi.fn();
  const session = { run: vi.fn(async () => ({ policy: expectedPolicy, value: expectedValue, dispose: disposed })), release: vi.fn(async () => { released(); }) };
  const runtime = { createSession: vi.fn(async () => session), dispose: vi.fn(async () => {}),
    resetProfile: vi.fn(),
    profile: () => ({ providers: { CPUExecutionProvider: 1 }, operators: { MatMul: 1 } }),
    info: { backend: 'wasm', adapter: null, features: [], runtimeBytes: 100 } };
  const pkg = { index: parseDeployment(deploymentFixture()), model: parseModel(modelFixture()), assetBase: 'https://example.test/models/', modelBase: 'https://example.test/models/hash/', packageHash: 'a'.repeat(64) };
  const deps = { load: vi.fn(async () => pkg), open: vi.fn(async () => runtime),
    read: vi.fn(async (_base: string, file: { path: string }) => file.path.includes('policy') ? new Uint8Array(expectedPolicy.buffer) : file.path.includes('value') ? new Uint8Array(expectedValue.buffer) : file.path.includes('initial') ? new Uint8Array(125388) : new Uint8Array(3)),
    now: () => performance.now() };
  return { engine: new InferenceEngine(deps), deps, runtime, session, disposed, released };
}

it('compares every output and releases every tensor and session after real work finishes', async () => {
  const f = setup();
  const result = await f.engine.infer(request());
  expect(result.comparison.policy).toMatchObject({ elements: POLICY_ELEMENTS, exceeded: 0, maxAbs: 0 });
  expect(result.comparison.value.elements).toBe(1);
  expect(result.value).toBe(-0.5);
  expect(result.metrics.samples).toHaveLength(1);
  expect(f.disposed).toHaveBeenCalledTimes(1);
  expect(f.released).toHaveBeenCalledTimes(1);
  await f.engine.infer({ ...request(), requestId: 2 });
  expect(f.deps.open).toHaveBeenCalledTimes(1); // runtime reused, session resources released
  expect(f.session.release).toHaveBeenCalledTimes(2);
  await f.engine.dispose();
  expect(f.runtime.dispose).toHaveBeenCalledTimes(1);
});

it('warms up ten times, measures thirty, and disposes outputs after all forty runs', async () => {
  const f = setup();
  const result = await f.engine.infer({ ...request(), iterations: 40 });
  expect(result.metrics.warmup).toBe(10);
  expect(result.metrics.samples).toHaveLength(30);
  expect(f.session.run).toHaveBeenCalledTimes(40);
  expect(f.disposed).toHaveBeenCalledTimes(40);
  expect(f.released).toHaveBeenCalledTimes(1);
});

it('reports the largest numerical error across every repetition', async () => {
  const f = setup();
  let first = true;
  f.session.run.mockImplementation(async () => {
    const policy = expectedPolicy.slice();
    if (first) policy[0] = policy[0]! + 0.000001;
    first = false;
    return { policy, value: expectedValue, dispose: f.disposed };
  });
  const result = await f.engine.infer({ ...request(), iterations: 40 });
  expect(result.comparison.policy.maxAbs).toBeGreaterThan(0.0000009);
});

it('uses the standard median and nearest-rank p95 after excluding warmup', async () => {
  const f = setup(); let calls = 0;
  f.deps.now = () => {
    const call = calls++;
    if (call < 3) return call;
    if (call >= 83) return 5000;
    const n = Math.floor((call - 3) / 2);
    return 100 + n * 100 + ((call - 3) % 2 ? n + 1 : 0);
  };
  const result = await f.engine.infer({ ...request(), iterations: 40 });
  expect(result.metrics.samples).toEqual(Array.from({ length: 30 }, (_, i) => i + 11));
  expect(result.metrics.medianMs).toBe(25.5);
  expect(result.metrics.p95Ms).toBe(39);
});

it('rejects a bad output at the last element and still releases tensors/session', async () => {
  const f = setup();
  const bad = expectedPolicy.slice(); bad[POLICY_ELEMENTS - 1] = 9;
  f.session.run.mockResolvedValue({ policy: bad, value: expectedValue, dispose: f.disposed });
  await expect(f.engine.infer(request())).rejects.toThrow(/tolerance/);
  expect(f.disposed).toHaveBeenCalledTimes(1); expect(f.released).toHaveBeenCalledTimes(1);
});

it('rejects nonfinite and incorrectly sized output without leaking the session', async () => {
  for (const policy of [new Float32Array([NaN]), new Float32Array(0), expectedPolicy.slice(1)]) {
    const f = setup(); f.session.run.mockResolvedValue({ policy, value: expectedValue, dispose: f.disposed });
    await expect(f.engine.infer(request())).rejects.toThrow();
    expect(f.disposed).toHaveBeenCalledTimes(1); expect(f.released).toHaveBeenCalledTimes(1);
  }
});

it('rejects obsolete packages, invalid choices and unbounded repeat counts before opening a backend', async () => {
  for (const change of [{ packageHash: 'b'.repeat(64) }, { variant: 'other' }, { fixture: 'missing' }, { iterations: 100000 }, { revision: -1 }]) {
    const f = setup();
    await expect(f.engine.infer({ ...request(), ...change })).rejects.toThrow();
    expect(f.deps.open).not.toHaveBeenCalled();
  }
});

it('never labels a CPU placement as WebGPU or silently switches a requested backend', async () => {
  const f = setup();
  await expect(f.engine.infer({ ...request(), backend: 'webgpu' })).rejects.toThrow(/placement|backend/);
  expect(f.released).toHaveBeenCalledTimes(1);
});
