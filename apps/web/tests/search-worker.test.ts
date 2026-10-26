import { afterEach, expect, it, vi } from 'vitest';

const { run, postMessage } = vi.hoisted(() => ({ run: vi.fn(), postMessage: vi.fn() }));
vi.mock('../src/wasm/pkg/voxelshogi_wasm.js', () => ({ default: vi.fn() }));
vi.mock('../src/ai/search-engine', () => ({ SearchEngine: class { run = run; } }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); vi.resetModules(); });

async function worker() {
  const scope = { onmessage: null as null | ((event: MessageEvent<unknown>) => void), postMessage };
  vi.stubGlobal('self', scope);
  await import('../src/ai/search.worker');
  return scope.onmessage!;
}

it('accepts the empty origin used by a dedicated Worker port and returns the engine reply', async () => {
  const handle = await worker();
  const input = { requestId: 7 }, reply = { kind: 'error', code: 'input' };
  run.mockResolvedValueOnce(reply);
  handle(new MessageEvent('message', { origin: '', data: input }));
  await vi.waitFor(() => expect(postMessage).toHaveBeenCalledWith(reply));
  expect(run).toHaveBeenCalledExactlyOnceWith(input);
});

it('rejects window-style origins before touching the search engine', async () => {
  const handle = await worker();
  run.mockResolvedValueOnce({ kind: 'error' });
  handle(new MessageEvent('message', { origin: 'https://untrusted.example', data: { requestId: 7 } }));
  expect(run).not.toHaveBeenCalled();
  expect(postMessage).not.toHaveBeenCalled();
});
