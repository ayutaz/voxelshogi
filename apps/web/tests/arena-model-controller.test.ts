// Scheduling and identity tests use a fake store, never Rust/model execution on Mac.
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ArenaController, DEFAULT_AI_OPTIONS } from '../src/ai/arena-controller';
import type { ModelCompleted, ModelDecision, ModelSeat } from '../src/ai/arena-model';
import { policyRequest, policyResult } from './policy-worker-fixtures';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
function selected(sourceId = 'local-1'): ModelSeat {
  const request = policyRequest();
  return { sourceId, selection: request.selection, files: request.files!, fixtures: ['initial-b', 'after-one-w'], repo: 'voxelshogi/model', revision: 'b'.repeat(40), sourceCommit: 'c'.repeat(40), license: 'Apache-2.0' };
}
function setup() {
  const state = { finished: false, side: 'b' as 'b' | 'w', ply: 0, moveCount: 0, revision: 1 };
  const listeners = new Set<() => void>();
  const store = { snapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    searchState: () => ({ revision: state.revision, cursor: state.ply, side: state.side, hash: '1'.repeat(16), ruleset: 'voxelshogi-standard-v1', recordJson: '{}' }),
    applyAiMove: vi.fn(() => { state.ply++; state.moveCount = state.ply; state.revision++; state.side = state.side === 'b' ? 'w' : 'b'; for (const listener of listeners) listener(); return { ok: true as const }; }),
  };
  const queue: { input: ModelDecision; resolve: (reply: ModelCompleted) => void }[] = [];
  const client = { policy: vi.fn((input: ModelDecision) => new Promise<ModelCompleted>(resolve => queue.push({ input, resolve }))),
    search: vi.fn(async () => { throw new Error('must not fall back to baseline'); }), retainModels: vi.fn(), cancel: vi.fn(), dispose: vi.fn() };
  const ai = new ArenaController(store, client), black = selected(), white = selected('local-2');
  const options = { ...DEFAULT_AI_OPTIONS, bDifficulty: 'model' as const, wDifficulty: 'model' as const, bModel: black, wModel: white, delayMs: 50 };
  ai.configure(options);
  function reply(index = queue.length - 1, change: Partial<ModelCompleted> = {}) {
    const input = queue[index]!.input, output = policyResult({ ...policyRequest(), root: input.root, selection: input.model.selection });
    queue[index]!.resolve({ ...output.result.root, kind: 'model-result', requestId: index + 1, model: { sourceId: input.model.sourceId, repo: input.model.repo, revision: input.model.revision, sourceCommit: input.model.sourceCommit, license: input.model.license, selection: { ...input.model.selection } },
      result: { bestMove: '111211', value: .25, rawAction: 0, rawLegal: false }, validation: output.validation, inferenceMs: 1, roundTripMs: 2, ...change });
  }
  return { ai, state, store, client, queue, options, black, white, reply };
}

it('steps a selected model exactly once and forwards its verified root and conditions', async () => {
  const f = setup(); expect(f.ai.step()).toBe(true);
  await vi.advanceTimersByTimeAsync(0);
  expect(f.client.policy).toHaveBeenCalledTimes(1);
  expect(f.queue[0]!.input).toMatchObject({ root: { revision: 1, cursor: 0, side: 'b' }, model: { sourceId: 'local-1' } });
  expect(f.client.search).not.toHaveBeenCalled();
  f.reply(); await vi.advanceTimersByTimeAsync(0);
  expect(f.store.applyAiMove).toHaveBeenCalledWith(expect.objectContaining({ revision: 1, cursor: 0, side: 'b', hash: '1'.repeat(16) }), '111211');
  expect(f.state.ply).toBe(1); expect(f.ai.snapshot()).toMatchObject({ phase: 'paused', last: { kind: 'model-result', model: { sourceId: 'local-1' } } }); f.ai.dispose();
});

it('ignores a late model result after pausing and resuming the same board and model', async () => {
  const f = setup(); f.ai.configure({ ...f.options, running: true });
  await vi.advanceTimersByTimeAsync(50); f.ai.pause();
  f.ai.configure({ ...f.options, running: true }); await vi.advanceTimersByTimeAsync(50);
  f.reply(0); await vi.advanceTimersByTimeAsync(0);
  expect(f.state.ply).toBe(0); expect(f.ai.snapshot().phase).toBe('thinking');
  f.reply(1); await vi.advanceTimersByTimeAsync(0); expect(f.state.ply).toBe(1); f.ai.dispose();
});

it('alternates independent selected models and never exposes a human seat as a retained AI', async () => {
  const f = setup(); f.ai.configure({ ...f.options, running: true });
  await vi.advanceTimersByTimeAsync(50); f.reply(); await vi.advanceTimersByTimeAsync(50);
  expect(f.queue[1]!.input.model.sourceId).toBe('local-2'); f.reply(); await vi.advanceTimersByTimeAsync(0);
  expect(f.state.ply).toBe(2);
  f.ai.configure({ ...f.options, mode: 'h-r', running: false });
  expect(f.client.retainModels).toHaveBeenLastCalledWith([f.white]); expect(f.ai.step()).toBe(false); f.ai.dispose();
});

for (const kind of ['format', 'source']) {
  it(`cancels a changed model ${kind} and ignores its late result on the same board`, async () => {
    const f = setup(); f.ai.configure({ ...f.options, running: true });
    await vi.advanceTimersByTimeAsync(50);
    const next = { ...f.black, selection: { ...f.black.selection }, sourceId: kind === 'source' ? 'local-3' : f.black.sourceId };
    if (kind === 'format') next.selection.precision = 'int8';
    f.ai.configure({ ...f.options, running: true, bModel: next });
    expect(f.client.cancel).toHaveBeenCalledTimes(1); f.reply(0); await vi.advanceTimersByTimeAsync(50);
    expect(f.state.ply).toBe(0); expect(f.queue[1]!.input.model).toMatchObject({ sourceId: next.sourceId, selection: next.selection });
    f.reply(1); await vi.advanceTimersByTimeAsync(0); expect(f.state.ply).toBe(1); f.ai.dispose();
  });
}

it('does not silently choose Normal when a selected model source is missing', async () => {
  const f = setup(); f.ai.configure({ ...f.options, bModel: undefined });
  f.ai.step(); await vi.advanceTimersByTimeAsync(0);
  expect(f.ai.snapshot().phase).toBe('error'); expect(f.client.search).not.toHaveBeenCalled(); expect(f.client.policy).not.toHaveBeenCalled(); f.ai.dispose();
});

it('rejects a model response for different conditions before touching the game', async () => {
  const f = setup(); f.ai.step(); await vi.advanceTimersByTimeAsync(0);
  f.reply(0, { model: { ...f.black, sourceId: 'unselected' } }); await vi.advanceTimersByTimeAsync(0);
  expect(f.store.applyAiMove).not.toHaveBeenCalled(); expect(f.ai.snapshot().phase).toBe('error'); f.ai.dispose();
});
