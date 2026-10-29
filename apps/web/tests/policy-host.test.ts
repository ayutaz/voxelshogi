import { expect, it, vi } from 'vitest';
import { PolicyWorkerHost } from '../src/inference/policy-host';
import { policyRequest, policyResult } from './policy-worker-fixtures';
import type { PolicyPosition } from '../src/inference/policy-session';

function setup() {
  const request = policyRequest();
  const session = { bestMove: vi.fn(async (root: PolicyPosition) => policyResult({ ...request, root }).result), dispose: vi.fn(async () => {}) };
  const create = vi.fn(async () => ({ session, validation: policyResult().validation }));
  const progress = vi.fn();
  return { host: new PolicyWorkerHost(create, progress), create, session, progress };
}

it('initializes once, reuses the validated session, and emits matched progress', async () => {
  const f = setup(), first = policyRequest();
  expect(await f.host.run(first)).toMatchObject({ kind: 'result', requestId: 1, result: { choice: { move: '111211' } } });
  expect(f.create).toHaveBeenCalledWith(first.files, first.selection, expect.any(Function));
  expect(f.progress.mock.calls.map(call => call[0].phase)).toEqual(['loading', 'running']);
  const next = { ...policyRequest(false), requestId: 2, root: { ...first.root, revision: 8 } };
  expect(await f.host.run(next)).toMatchObject({ kind: 'result', requestId: 2, result: { root: { revision: 8 } } });
  expect(f.create).toHaveBeenCalledTimes(1); expect(f.session.bestMove).toHaveBeenCalledTimes(2);
  await f.host.dispose(); expect(f.session.dispose).toHaveBeenCalledTimes(1);
});

it('rejects missing files, invalid metadata, and model/backend changes without another initialization', async () => {
  const f = setup();
  expect(await f.host.run(policyRequest(false))).toMatchObject({ kind: 'error', code: 'input' });
  expect(await f.host.run({ ...policyRequest(), requestId: 0 })).toMatchObject({ kind: 'error', code: 'input' });
  expect(f.create).not.toHaveBeenCalled();
  await f.host.run(policyRequest());
  const next = policyRequest(false); next.requestId = 2; next.selection.backend = 'webgpu';
  expect(await f.host.run(next)).toMatchObject({ kind: 'error', code: 'input' });
  expect(f.create).toHaveBeenCalledTimes(1); await f.host.dispose();
});

it('reports busy without cancelling the already accepted initialization', async () => {
  const f = setup(); let finish!: (ready: Awaited<ReturnType<typeof f.create>>) => void;
  f.create.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const first = f.host.run(policyRequest());
  const next = { ...policyRequest(), requestId: 2 };
  expect(await f.host.run(next)).toMatchObject({ kind: 'error', requestId: 2, code: 'busy' });
  finish({ session: f.session, validation: policyResult().validation });
  expect(await first).toMatchObject({ kind: 'result', requestId: 1 });
  expect(f.session.dispose).not.toHaveBeenCalled(); await f.host.dispose();
});

it('disposes failed inference and prevents implicit retries on another backend', async () => {
  const f = setup(); f.session.bestMove.mockRejectedValueOnce(new Error('execution failed'));
  expect(await f.host.run(policyRequest())).toMatchObject({ kind: 'error', code: 'inference', message: 'execution failed' });
  expect(f.session.dispose).toHaveBeenCalledTimes(1);
  expect(await f.host.run(policyRequest())).toMatchObject({ kind: 'error' });
  expect(f.create).toHaveBeenCalledTimes(1);
});

it('reports initialization failure separately and bounds error text', async () => {
  const f = setup(); f.create.mockRejectedValueOnce(new Error('x'.repeat(600)));
  const result = await f.host.run(policyRequest());
  expect(result).toMatchObject({ kind: 'error', code: 'initialization' });
  expect('message' in result && result.message.length).toBe(500);
  expect(f.session.bestMove).not.toHaveBeenCalled();
});

it('disposes a late-created session after cancellation without publishing a result', async () => {
  const f = setup(); let finish!: (ready: Awaited<ReturnType<typeof f.create>>) => void;
  f.create.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = f.host.run(policyRequest());
  await f.host.dispose(); finish({ session: f.session, validation: policyResult().validation });
  expect(await pending).toMatchObject({ kind: 'error' });
  expect(f.session.bestMove).not.toHaveBeenCalled(); expect(f.session.dispose).toHaveBeenCalledTimes(1);
});

it('still reports a failed move when resource cleanup also fails', async () => {
  const f = setup();
  f.session.bestMove.mockRejectedValueOnce(new Error('execution failed'));
  f.session.dispose.mockRejectedValueOnce(new Error('release failed'));
  const reply = await f.host.run(policyRequest());
  expect(reply).toMatchObject({ kind: 'error', code: 'inference' });
  expect('message' in reply && reply.message).toMatch(/cleanup/);
});
