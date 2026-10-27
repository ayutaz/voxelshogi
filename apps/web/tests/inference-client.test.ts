import { expect, it, vi } from 'vitest';
import type { InferenceWorkerPort as WorkerPort } from '../src/inference/client';
import type { InferenceRequest } from '../src/inference/engine';
import { InferenceClient } from '../src/inference/client';

const input = { revision: 2, packageHash: 'a'.repeat(64), variant: 'fp32', fixture: 'initial-b', backend: 'wasm', iterations: 1 } as const;
const request = (id: number) => ({ ...input, requestId: id, kind: 'infer', schema: 1 }) as InferenceRequest;
function port() { return { onmessage: null, onerror: null, onmessageerror: null, postMessage: vi.fn(), terminate: vi.fn() } as WorkerPort & { postMessage: ReturnType<typeof vi.fn>; terminate: ReturnType<typeof vi.fn> }; }
function message(w: WorkerPort, data: unknown) { w.onmessage?.({ data } as MessageEvent); }
function success(r = request(1)) {
  const report = (elements: number) => ({ elements, exceeded: 0, maxAbs: 0, maxRelative: 0, atol: 1e-5, rtol: 1e-4 });
  return { kind: 'result', result: { request: r, value: 0.25, comparison: { policy: report(1_067_985), value: report(1) },
    metrics: { samples: [3], warmup: 0, medianMs: 3, p95Ms: 3, loadMs: 1, initMs: 2, totalMs: 10, tensorBytes: 4397332, resources: [] },
    information: { backend: 'wasm', adapter: null, features: [], runtimeBytes: 100 }, profile: { providers: { CPUExecutionProvider: 1 }, operators: { MatMul: 1 } }, buffers: null } };
}

it('creates lazily, forwards verified progress, ignores duplicate IDs and reuses an idle Worker', async () => {
  const w = port(), factory = vi.fn(() => w), progress = vi.fn();
  const client = new InferenceClient(factory);
  expect(factory).not.toHaveBeenCalled();
  const first = client.infer(input, progress);
  await expect(client.infer(input)).rejects.toThrow(/busy/);
  message(w, { kind: 'progress', request: request(1), phase: 'running', atUnixMs: 100 });
  expect(progress).toHaveBeenCalledWith('running', 100);
  message(w, success(request(99))); message(w, success());
  expect((await first).value).toBe(0.25);
  const second = client.infer(input); message(w, success()); message(w, success(request(2)));
  await second; expect(factory).toHaveBeenCalledTimes(1);
  client.dispose(); await expect(client.infer(input)).rejects.toThrow(/disposed/);
});

it('terminates on cancel and ignores queued old progress, errors and results during a newer request', async () => {
  const old = port(), fresh = port(), factory = vi.fn().mockReturnValueOnce(old).mockReturnValueOnce(fresh);
  const client = new InferenceClient(factory), progress = vi.fn();
  const first = client.infer(input);
  const rejection = expect(first).rejects.toMatchObject({ name: 'AbortError' });
  const callback = old.onmessage!, error = old.onerror!;
  client.cancel(); await rejection; expect(old.terminate).toHaveBeenCalledTimes(1);
  const second = client.infer(input, progress);
  callback({ data: { kind: 'progress', request: request(2), phase: 'running', atUnixMs: 100 } } as MessageEvent);
  callback({ data: success(request(2)) } as MessageEvent);
  error({ preventDefault: vi.fn(), message: 'old failure' } as unknown as ErrorEvent);
  expect(progress).not.toHaveBeenCalled();
  message(fresh, success(request(2))); await second;
  client.dispose(); expect(fresh.terminate).toHaveBeenCalledTimes(1);
});

for (const changed of [{ revision: 1 }, { packageHash: 'b'.repeat(64) }, { backend: 'webgpu' }, { variant: 'fp16' }, { fixture: 'other' }]) {
  it(`rejects a same-ID response for a different root ${JSON.stringify(changed)}`, async () => {
    const w = port(), client = new InferenceClient(() => w), pending = client.infer(input);
    const rejection = expect(pending).rejects.toThrow(/protocol/);
    message(w, success({ ...request(1), ...changed } as InferenceRequest)); await rejection;
    expect(w.terminate).toHaveBeenCalledTimes(1);
  });
}

for (const failure of ['nan', 'sample-count', 'comparison', 'provider']) {
  it(`rejects a malformed inference result: ${failure}`, async () => {
    const w = port(), client = new InferenceClient(() => w), pending = client.infer(input);
    const rejection = expect(pending).rejects.toThrow(/protocol/);
    const reply = success();
    if (failure === 'nan') reply.result.value = NaN;
    if (failure === 'sample-count') reply.result.metrics.samples = [];
    if (failure === 'comparison') reply.result.comparison.policy.elements = 1;
    if (failure === 'provider') reply.result.profile.providers = { WebGpuExecutionProvider: 1 } as unknown as typeof reply.result.profile.providers;
    message(w, reply); await rejection; expect(w.terminate).toHaveBeenCalledTimes(1);
  });
}
