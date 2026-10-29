import { expect, it, vi } from 'vitest';
import { ArenaClient } from '../src/ai/arena-client';
import type { ModelSeat } from '../src/ai/arena-model';
import type { PolicySource, PolicyClientResult } from '../src/inference/policy-client';
import type { SearchInput } from '../src/ai/search-protocol';
import type { SearchClient } from '../src/ai/search-client';
import type { PolicyPosition } from '../src/inference/policy-session';
import { policyRequest, policyResult } from './policy-worker-fixtures';

function seat(sourceId = 'local-1'): ModelSeat {
  const request = policyRequest();
  return { sourceId, selection: request.selection, files: request.files!, fixtures: ['initial-b', 'after-one-w'], repo: 'voxelshogi/model', revision: 'b'.repeat(40), sourceCommit: 'c'.repeat(40), license: 'Apache-2.0' };
}
function modelClient() {
  return { bestMove: vi.fn(async (root: PolicyPosition) => ({ ...policyResult({ ...policyRequest(), root }), roundTripMs: 3 }) as PolicyClientResult),
    cancel: vi.fn(), dispose: vi.fn() };
}
function setup() {
  const baseline = { search: vi.fn<SearchClient['search']>(async () => { throw new Error('baseline placeholder'); }), cancel: vi.fn(), dispose: vi.fn() };
  const model = modelClient(), create = vi.fn<(source: PolicySource) => Promise<typeof model>>(async () => model);
  return { client: new ArenaClient(baseline, create), baseline, model, create };
}

it('routes selected models lazily and reuses one client when both seats share the same source/format/backend', async () => {
  const f = setup(), selected = seat();
  f.client.retainModels([selected, selected]); expect(f.create).not.toHaveBeenCalled();
  const first = await f.client.policy({ root: policyRequest().root, model: selected });
  expect(first).toMatchObject({ kind: 'model-result', side: 'b', model: { sourceId: 'local-1', selection: selected.selection }, result: { bestMove: '111211', value: .25 } });
  await f.client.policy({ root: { ...policyRequest().root, revision: 8 }, model: selected });
  expect(f.create).toHaveBeenCalledTimes(1); expect(f.model.bestMove).toHaveBeenCalledTimes(2);
  expect(f.baseline.search).not.toHaveBeenCalled(); f.client.dispose(); expect(f.model.dispose).toHaveBeenCalledTimes(1);
});

it('keeps baseline search independent of the lazy model module', async () => {
  const f = setup();
  const input: SearchInput = { ...policyRequest().root, schema: 1, kind: 'search', difficulty: 'normal', seed: 42, limits: { maxDepth: 2 } };
  const reply = { ...input, kind: 'result' as const, requestId: 1, result: { schema: 1 as const, bestMove: '111211', score: 0, completedDepth: 1, nodes: '1', lastIterationNodes: '1', ttHits: '0', stopReason: 'depth' as const },
    metrics: { initMs: 0, replayMs: 0, searchMs: 1, totalMs: 1 }, roundTripMs: 1 };
  f.baseline.search.mockResolvedValueOnce(reply);
  expect(await f.client.search(input)).toBe(reply);
  expect(f.create).not.toHaveBeenCalled(); f.client.dispose();
});

it('replaces a reselected directory even when model ID and manifest hash are identical', async () => {
  const f = setup(), first = seat(), next = seat('local-2');
  f.client.retainModels([first]); await f.client.policy({ root: policyRequest().root, model: first });
  f.client.retainModels([next]); expect(f.model.dispose).toHaveBeenCalledTimes(1);
  const fresh = modelClient(); f.create.mockResolvedValueOnce(fresh);
  await f.client.policy({ root: policyRequest().root, model: next });
  expect(f.create).toHaveBeenCalledTimes(2); expect(fresh.bestMove).toHaveBeenCalledTimes(1); f.client.dispose();
});

it('keeps distinct precision/backend sessions and refuses a third seat or an unselected model', async () => {
  const f = setup(), black = seat(), white = seat(); white.selection = { ...white.selection, precision: 'int8' };
  f.client.retainModels([black, white]);
  await f.client.policy({ root: policyRequest().root, model: black });
  const second = modelClient();
  second.bestMove.mockImplementation(async root => ({ ...policyResult({ ...policyRequest(), root, selection: white.selection }), roundTripMs: 3 }) as PolicyClientResult);
  f.create.mockResolvedValueOnce(second);
  expect((await f.client.policy({ root: policyRequest().root, model: white })).model.selection.precision).toBe('int8');
  expect(f.create).toHaveBeenCalledTimes(2);
  expect(() => f.client.retainModels([black, white, seat('third')])).toThrow();
  await expect(f.client.policy({ root: policyRequest().root, model: seat('unknown') })).rejects.toThrow(); f.client.dispose();
});

it('cancels before a lazy import finishes and disposes its late client without starting a Worker', async () => {
  const f = setup(), selected = seat(); let finish!: (client: typeof f.model) => void;
  f.create.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  f.client.retainModels([selected]);
  const pending = f.client.policy({ root: policyRequest().root, model: selected });
  f.client.cancel(); finish(f.model);
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  expect(f.model.bestMove).not.toHaveBeenCalled(); expect(f.model.dispose).toHaveBeenCalledTimes(1); f.client.dispose();
});

it('does not let completion of an old lazy load clear a newer in-flight operation', async () => {
  const f = setup(), selected = seat(), fresh = modelClient();
  let finishOld!: (client: typeof f.model) => void, finishNew!: (client: typeof fresh) => void;
  f.create.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }))
    .mockImplementationOnce(() => new Promise(resolve => { finishNew = resolve; }));
  f.client.retainModels([selected]);
  const old = f.client.policy({ root: policyRequest().root, model: selected }), oldRejected = expect(old).rejects.toMatchObject({ name: 'AbortError' });
  f.client.cancel();
  const next = f.client.policy({ root: { ...policyRequest().root, revision: 8 }, model: selected });
  finishOld(f.model); await oldRejected;
  await expect(f.client.policy({ root: policyRequest().root, model: selected })).rejects.toThrow(/busy/);
  finishNew(fresh);
  await expect(next).resolves.toMatchObject({ revision: 8, result: { bestMove: '111211' } }); f.client.dispose();
});

it('rejects late cancelled moves without returning their choices', async () => {
  const f = setup(), selected = seat();
  f.client.retainModels([selected]);
  let finish!: (reply: PolicyClientResult) => void;
  f.model.bestMove.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = f.client.policy({ root: policyRequest().root, model: selected });
  await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
  selected.repo = 'changed/model'; f.client.cancel();
  finish({ ...policyResult(), roundTripMs: 3 } as PolicyClientResult);
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  expect(f.model.cancel).toHaveBeenCalledTimes(1); f.client.dispose();
});

it('snapshots model/source conditions before asynchronous client creation', async () => {
  const f = setup(), selected = seat(); let finish!: (client: typeof f.model) => void;
  f.create.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  f.client.retainModels([selected]);
  const pending = f.client.policy({ root: policyRequest().root, model: selected });
  selected.repo = 'changed/model'; selected.selection.backend = 'webgpu'; selected.files[0]!.path = '../wrong';
  finish(f.model);
  const reply = await pending;
  expect(reply.model.repo).toBe('voxelshogi/model'); expect(reply.model.selection.backend).toBe('wasm');
  expect(f.create.mock.calls[0]![0].files[0]!.path).toBe('download/manifest.json'); f.client.dispose();
});

it('never substitutes Normal when a model client cannot load', async () => {
  const f = setup(), selected = seat(); f.client.retainModels([selected]);
  f.create.mockRejectedValueOnce(new Error('model could not load'));
  await expect(f.client.policy({ root: policyRequest().root, model: selected })).rejects.toThrow('model could not load');
  expect(f.baseline.search).not.toHaveBeenCalled(); f.client.dispose();
});

it('rejects a missing source ID before retaining or loading a model', () => {
  const f = setup(), invalid = seat(); invalid.sourceId = undefined as unknown as string;
  expect(() => f.client.retainModels([invalid])).toThrow(); expect(f.create).not.toHaveBeenCalled(); f.client.dispose();
});
