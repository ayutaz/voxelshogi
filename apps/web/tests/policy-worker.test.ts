import { afterEach, expect, it, vi } from 'vitest';

const { run, postMessage } = vi.hoisted(() => ({ run: vi.fn(), postMessage: vi.fn() }));
vi.mock('../src/inference/policy-factory', () => ({ createPolicyRuntime: vi.fn() }));
vi.mock('../src/inference/policy-host', () => ({ PolicyWorkerHost: class { run = run; } }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); vi.resetModules(); });

async function worker() {
  const scope = { onmessage: null as null | ((event: MessageEvent<unknown>) => void), postMessage };
  vi.stubGlobal('self', scope);
  await import('../src/inference/policy.worker');
  return scope.onmessage!;
}
it('accepts only a dedicated-Worker port and returns the host response', async () => {
  const handle = await worker(), input = { requestId: 7 }, reply = { schema: 1, kind: 'error', requestId: 7 };
  run.mockResolvedValueOnce(reply);
  handle(new MessageEvent('message', { origin: '', data: input }));
  await vi.waitFor(() => expect(postMessage).toHaveBeenCalledWith(reply));
  expect(run).toHaveBeenCalledExactlyOnceWith(input);
});
it('ignores window-style origins before looking at files or creating a model', async () => {
  const handle = await worker();
  run.mockResolvedValueOnce({ kind: 'error' });
  handle(new MessageEvent('message', { origin: 'https://untrusted.example', data: { requestId: 7 } }));
  expect(run).not.toHaveBeenCalled(); expect(postMessage).not.toHaveBeenCalled();
});
