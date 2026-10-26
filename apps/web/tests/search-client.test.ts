import { describe, expect, it, vi } from 'vitest';
import { SearchClient } from '../src/ai/search-client';
import type { SearchInput, SearchSuccess, WorkerPort } from '../src/ai/search-protocol';

const input: SearchInput = { schema: 1, kind: 'search', revision: 7, ruleset: 'voxelshogi-standard-v1',
  recordJson: '{}', cursor: 0, hash: '043b66e12f6b84fd', side: 'b', difficulty: 'normal', seed: 42,
  limits: { maxDepth: 2, maxNodes: 100 } };
function port() {
  return { onmessage: null, onerror: null, onmessageerror: null, postMessage: vi.fn(), terminate: vi.fn() } as WorkerPort & { postMessage: ReturnType<typeof vi.fn>; terminate: ReturnType<typeof vi.fn> };
}
function success(requestId: number): SearchSuccess {
  return { ...input, kind: 'result', requestId,
    result: { schema: 1, bestMove: '577567', score: 0, completedDepth: 1, nodes: '8', lastIterationNodes: '8', ttHits: '0', stopReason: 'nodes' },
    metrics: { initMs: 1, replayMs: 2, searchMs: 3, totalMs: 6 } };
}
function message(w: WorkerPort, data: unknown) { w.onmessage?.({ data } as MessageEvent); }

describe('SearchClient', () => {
  it('lazily creates one worker, accepts only one request, and reuses it', async () => {
    const w = port(); const factory = vi.fn(() => w);
    const client = new SearchClient(factory);
    expect(factory).not.toHaveBeenCalled();
    const first = client.search(input);
    expect(factory).toHaveBeenCalledTimes(1);
    expect(w.postMessage).toHaveBeenCalledWith({ ...input, requestId: 1 });
    const overlap = expect(client.search(input)).rejects.toThrow(/busy/);
    message(w, success(99)); // unrelated/queued response cannot complete this request
    message(w, success(1));
    message(w, success(2));
    await overlap;
    expect(await first).toMatchObject({ requestId: 1, result: { bestMove: '577567' } });
    const second = client.search(input);
    message(w, success(1)); // duplicate response must not complete request 2
    message(w, success(2));
    expect((await second).requestId).toBe(2);
    expect(factory).toHaveBeenCalledTimes(1);
    client.dispose();
    expect(w.terminate).toHaveBeenCalledTimes(1);
    await expect(client.search(input)).rejects.toThrow(/disposed/);
  });

  it('terminates on cancel, rejects the pending promise, and ignores already queued callbacks', async () => {
    const old = port(), fresh = port();
    const factory = vi.fn().mockReturnValueOnce(old).mockReturnValueOnce(fresh);
    const client = new SearchClient(factory);
    const pending = client.search(input);
    const rejection = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    const queued = old.onmessage!;
    const queuedError = old.onerror!;
    const queuedDecodeError = old.onmessageerror!;
    client.cancel();
    await rejection;
    expect(old.terminate).toHaveBeenCalledTimes(1);
    const second = client.search({ ...input, revision: 8 });
    queued({ data: success(1) } as MessageEvent);
    queued({ data: { ...success(2), revision: 8, result: { ...success(2).result, score: 1_000_000 } } } as MessageEvent);
    queuedError({ message: 'old failure', preventDefault: vi.fn() } as unknown as ErrorEvent);
    queuedDecodeError({} as MessageEvent);
    message(fresh, { ...success(2), revision: 8 });
    expect(await second).toMatchObject({ revision: 8, result: { score: 0 } });
    client.dispose();
    client.dispose();
    expect(fresh.terminate).toHaveBeenCalledTimes(1);
  });

  for (const changed of [{ revision: 6 }, { hash: '0000000000000000' }, { side: 'w' }, { ruleset: 'another-rule' }, { cursor: 1 }]) {
    it(`rejects same-ID response with wrong root ${JSON.stringify(changed)}`, async () => {
      const w = port(); const client = new SearchClient(() => w);
      const promise = client.search(input);
      const rejection = expect(promise).rejects.toThrow(/protocol/);
      message(w, { ...success(1), ...changed });
      await rejection;
      expect(w.terminate).toHaveBeenCalledTimes(1);
      client.dispose();
    });
  }

  for (const bad of [null, {}, { schema: 2 }, { ...success(1), result: { nodes: 'NaN' } },
    { ...success(1), result: { ...success(1).result, nodes: '9007199254740993' } },
    { ...success(1), metrics: { initMs: 0, replayMs: -1, searchMs: 0, totalMs: 0 } },
    ...[NaN, Infinity, -1, 0, 1.5, 2 ** 53].map((requestId) => ({ ...success(1), requestId }))]) {
    it(`rejects malformed messages ${JSON.stringify(bad)?.slice(0, 40)}`, async () => {
      const w = port(); const client = new SearchClient(() => w);
      const promise = client.search(input);
      const rejection = expect(promise).rejects.toThrow(/protocol/);
      message(w, bad);
      message(w, success(1)); // malformed identity must fail, rather than wait for a later valid reply
      await rejection;
      client.dispose();
    });
  }

  it('reports worker errors, message decode errors and creation/post failures; next request recreates', async () => {
    for (const failure of ['error', 'messageerror', 'post', 'create']) {
      const w = port(), fresh = port();
      if (failure === 'post') w.postMessage.mockImplementation(() => { throw new Error('post failed'); });
      const factory = vi.fn().mockImplementationOnce(() => { if (failure === 'create') throw new Error('create failed'); return w; }).mockReturnValue(fresh);
      const client = new SearchClient(factory);
      const promise = client.search(input);
      const rejection = expect(promise).rejects.toThrow();
      if (failure === 'error') w.onerror?.({ message: 'wasm init failed', preventDefault: vi.fn() } as unknown as ErrorEvent);
      if (failure === 'messageerror') w.onmessageerror?.({} as MessageEvent);
      await rejection;
      const retry = client.search(input);
      message(fresh, success(2));
      expect((await retry).requestId).toBe(2);
      client.dispose();
    }
  });

  it('propagates an explicit search error without silently substituting Easy', async () => {
    const w = port(); const client = new SearchClient(() => w);
    const promise = client.search(input);
    const rejection = expect(promise).rejects.toThrow('invalid record');
    message(w, { ...input, requestId: 1, kind: 'error', code: 'input', message: 'invalid record' });
    await rejection;
    expect(w.terminate).toHaveBeenCalledTimes(1);
    client.dispose();
  });
});
