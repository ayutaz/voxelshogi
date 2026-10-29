import { expect, it, vi } from 'vitest';
import { PolicyClient, type PolicyWorkerPort } from '../src/inference/policy-client';
import type { PolicyRequest } from '../src/inference/policy-protocol';
import { policyRequest, policyResult } from './policy-worker-fixtures';

function port() {
  return { onmessage: null, onerror: null, onmessageerror: null, postMessage: vi.fn(), terminate: vi.fn() } as PolicyWorkerPort & { postMessage: ReturnType<typeof vi.fn>; terminate: ReturnType<typeof vi.fn> };
}
function source() { const request = policyRequest(); return { selection: request.selection, files: request.files!, fixtures: ['initial-b', 'after-one-w'] }; }
const requestAt = (worker: ReturnType<typeof port>, index = 0) => worker.postMessage.mock.calls[index]![0] as PolicyRequest;
const message = (worker: PolicyWorkerPort, data: unknown) => worker.onmessage?.({ data } as MessageEvent);

it('lazily creates one Worker, sends File handles only on the first turn, and validates before reuse', async () => {
  const worker = port(), create = vi.fn(() => worker), input = source(), read = vi.spyOn(input.files[0]!.file, 'arrayBuffer');
  const client = new PolicyClient(input, create);
  expect(create).not.toHaveBeenCalled();
  const first = client.bestMove(policyRequest().root);
  await expect(client.bestMove(policyRequest().root)).rejects.toThrow(/busy/);
  expect(requestAt(worker).files![0]!.file).toBe(input.files[0]!.file);
  message(worker, policyResult({ ...requestAt(worker), requestId: 99 }));
  message(worker, policyResult(requestAt(worker)));
  await expect(first).resolves.toMatchObject({ result: { choice: { move: '111211' } } });
  const second = client.bestMove({ ...policyRequest().root, revision: 8 });
  expect(requestAt(worker, 1).files).toBeUndefined();
  message(worker, policyResult(requestAt(worker))); // duplicate old response
  message(worker, policyResult(requestAt(worker, 1)));
  expect((await second).result.root.revision).toBe(8); expect(create).toHaveBeenCalledTimes(1);
  expect(read).not.toHaveBeenCalled(); client.dispose();
  expect(worker.terminate).toHaveBeenCalledTimes(1);
});

it('terminates on cancellation and ignores queued messages/errors from an obsolete Worker', async () => {
  const old = port(), fresh = port(), create = vi.fn().mockReturnValueOnce(old).mockReturnValueOnce(fresh);
  const client = new PolicyClient(source(), create), progress = vi.fn();
  const first = client.bestMove(policyRequest().root), rejected = expect(first).rejects.toMatchObject({ name: 'AbortError' });
  const queued = old.onmessage!, queuedError = old.onerror!, queuedDecode = old.onmessageerror!;
  client.cancel(); await rejected;
  const second = client.bestMove({ ...policyRequest().root, revision: 8 }, progress), request = requestAt(fresh);
  const forged = policyResult(request); forged.result.choice.value = .75;
  queued({ data: forged } as MessageEvent);
  queued({ data: { schema: 1, kind: 'progress', requestId: request.requestId, selection: request.selection, root: forged.result.root, phase: 'loading' } } as MessageEvent);
  queuedError({ message: 'old failure', preventDefault: vi.fn() } as unknown as ErrorEvent);
  queuedDecode({} as MessageEvent);
  expect(progress).not.toHaveBeenCalled();
  expect(request.files).toBeDefined();
  message(fresh, policyResult(request));
  await expect(second).resolves.toMatchObject({ result: { choice: { value: .25 } } });
  expect(old.terminate).toHaveBeenCalledTimes(1); client.dispose(); client.dispose();
  expect(fresh.terminate).toHaveBeenCalledTimes(1);
  await expect(client.bestMove(policyRequest().root)).rejects.toThrow(/disposed/);
});

it('passes only current, fully matched progress and rejects malformed results before applying them', async () => {
  const worker = port(), client = new PolicyClient(source(), () => worker), progress = vi.fn();
  const pending = client.bestMove(policyRequest().root, progress), request = requestAt(worker), reply = policyResult(request);
  message(worker, { schema: 1, kind: 'progress', requestId: request.requestId, selection: request.selection, root: reply.result.root, phase: 'validating' });
  expect(progress).toHaveBeenCalledExactlyOnceWith('validating');
  reply.validation.fixtures[0]!.comparison.policy.exceeded = 1;
  message(worker, reply);
  await expect(pending).rejects.toThrow(/protocol/); expect(worker.terminate).toHaveBeenCalledTimes(1);
});

it('rejects invalid IDs, cross-format replies, and invalid roots rather than hanging or falling back', async () => {
  for (const field of ['id', 'precision', 'revision']) {
    const worker = port(), client = new PolicyClient(source(), () => worker);
    const pending = client.bestMove(policyRequest().root), reply = policyResult(requestAt(worker));
    if (field === 'id') reply.requestId = 0;
    if (field === 'precision') reply.result.selection.precision = 'int8';
    if (field === 'revision') reply.result.root.revision++;
    message(worker, reply);
    await expect(pending).rejects.toThrow(/protocol/); expect(worker.terminate).toHaveBeenCalledTimes(1);
  }
});

it('rejects malformed inputs before creating a Worker and snapshots mutable source metadata', async () => {
  const worker = port(), create = vi.fn(() => worker), input = source(), client = new PolicyClient(input, create);
  await expect(client.bestMove({ ...policyRequest().root, revision: -1 })).rejects.toThrow();
  expect(create).not.toHaveBeenCalled();
  input.selection.backend = 'webgpu'; input.files[0]!.path = '../secret'; input.fixtures.length = 0;
  const pending = client.bestMove(policyRequest().root);
  void pending.catch(() => {}); // Keep a failed assertion from leaving an unhandled fixture promise.
  expect(create).toHaveBeenCalledTimes(1);
  const request = requestAt(worker);
  expect(request.selection.backend).toBe('wasm'); expect(request.files![0]!.path).toBe('download/manifest.json');
  message(worker, policyResult(request)); await pending; client.dispose();
});

it('closes the Worker after decode, execution or postMessage failures', async () => {
  for (const kind of ['decode', 'execution', 'post']) {
    const worker = port(), client = new PolicyClient(source(), () => worker);
    if (kind === 'post') worker.postMessage.mockImplementationOnce(() => { throw new Error('post failed'); });
    const pending = client.bestMove(policyRequest().root);
    if (kind === 'decode') worker.onmessageerror?.({} as MessageEvent);
    if (kind === 'execution') worker.onerror?.({ message: 'Worker failed', preventDefault: vi.fn() } as unknown as ErrorEvent);
    await expect(pending).rejects.toThrow(); expect(worker.terminate).toHaveBeenCalledTimes(1);
  }
});

it('carries the expected storage-only mode into independent response validation', async () => {
  const worker = port(), input = source(); input.selection.precision = 'fp16'; input.selection.backend = 'webgpu';
  const client = new PolicyClient({ ...input, fp16WeightOnly: true }, () => worker);
  const pending = client.bestMove(policyRequest().root), result = policyResult(requestAt(worker));
  Reflect.set(result.validation, 'fp16WeightOnly', true);
  Reflect.set(result.validation.information, 'computePrecision', 'float32');
  Reflect.set(result.validation.information, 'adapter', { vendor: 'fake', architecture: '', device: '', description: '' });
  Reflect.set(result.validation.profile, 'providers', { WebGpuExecutionProvider: 1 });
  message(worker, result); await expect(pending).resolves.toMatchObject({ validation: { fp16WeightOnly: true } });
  client.dispose();
});
