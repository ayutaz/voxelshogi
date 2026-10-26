import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadWasm } from './loadWasm';
import { GameStore } from '../src/game/store';
import { ArenaController, DEFAULT_AI_OPTIONS, type ArenaOptions } from '../src/ai/arena-controller';
import type { SearchInput, SearchSuccess } from '../src/ai/search-protocol';

beforeAll(loadWasm);
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
function setup(options: Partial<ArenaOptions> = {}) {
  const s = new GameStore();
  const queue: { input: SearchInput; resolve: (reply: SearchSuccess & { roundTripMs: number }) => void; reject: (error: Error) => void }[] = [];
  const client = { search: vi.fn((input: SearchInput) => new Promise<SearchSuccess & { roundTripMs: number }>((resolve, reject) => { queue.push({ input, resolve, reject }); })), cancel: vi.fn(), dispose: vi.fn() };
  const ai = new ArenaController(s, client);
  ai.configure({ ...DEFAULT_AI_OPTIONS, delayMs: 100, ...options });
  function reply(index = queue.length - 1, move?: string) {
    const q = queue[index]!;
    q.resolve({ ...q.input, kind: 'result', requestId: index + 1, roundTripMs: 12,
      result: { schema: 1, bestMove: move ?? (s.snapshot().side === 'b' ? '577567' : '533543'), score: 0, completedDepth: 1, nodes: '8', lastIterationNodes: '8', ttHits: '0', stopReason: 'depth' },
      metrics: { initMs: 1, replayMs: 1, searchMs: 8, totalMs: 10 } });
  }
  return { s, ai, client, queue, reply };
}

describe('ArenaController', () => {
  it('starts paused, permits one asynchronous step, and remains paused after exactly one ply', async () => {
    const { s, ai, client, reply } = setup();
    expect(ai.snapshot().phase).toBe('paused');
    expect(ai.step()).toBe(true);
    expect(ai.step()).toBe(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(client.search).toHaveBeenCalledTimes(1);
    expect(ai.snapshot().phase).toBe('thinking');
    expect(s.snapshot().ply).toBe(0);
    reply(); await vi.advanceTimersByTimeAsync(0);
    expect(s.snapshot().ply).toBe(1);
    expect(ai.snapshot().phase).toBe('paused');
    await vi.advanceTimersByTimeAsync(10_000);
    expect(client.search).toHaveBeenCalledTimes(1);
    ai.dispose();
  });

  for (const b of ['easy', 'normal'] as const) for (const w of ['easy', 'normal'] as const) {
    it(`schedules ${b}/${w} turns with display delay separate from search limits`, async () => {
      const { s, ai, client, queue, reply } = setup({ running: true, bDifficulty: b, wDifficulty: w });
      await vi.advanceTimersByTimeAsync(99);
      expect(client.search).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(1);
      expect(queue[0]!.input).toMatchObject({ difficulty: b, side: 'b', limits: DEFAULT_AI_OPTIONS.limits });
      reply(); await vi.advanceTimersByTimeAsync(100);
      expect(queue[1]!.input).toMatchObject({ difficulty: w, side: 'w' });
      reply(); await vi.advanceTimersByTimeAsync(0);
      expect(s.snapshot().ply).toBe(2);
      expect(client.cancel).not.toHaveBeenCalled(); // successful turns reuse the worker
      ai.dispose();
    });
  }

  it('pause cancels thinking, and late success cannot play even after resuming the same board', async () => {
    const { s, ai, client, reply } = setup({ running: true });
    await vi.advanceTimersByTimeAsync(100);
    ai.pause();
    expect(client.cancel).toHaveBeenCalledTimes(1);
    ai.configure({ ...DEFAULT_AI_OPTIONS, running: true, delayMs: 100 });
    await vi.advanceTimersByTimeAsync(100);
    reply(0); await vi.advanceTimersByTimeAsync(0);
    expect(s.snapshot().ply).toBe(0);
    expect(ai.snapshot().phase).toBe('thinking');
    reply(1); await vi.advanceTimersByTimeAsync(0);
    expect(s.snapshot().ply).toBe(1);
    ai.dispose();
  });

  it('explicit pause cancels a single-step search even though automatic playback is already paused', async () => {
    const { s, ai, client, reply } = setup();
    ai.step(); await vi.advanceTimersByTimeAsync(0);
    ai.pause();
    expect(client.cancel).toHaveBeenCalledTimes(1);
    reply(); await vi.advanceTimersByTimeAsync(0);
    expect(s.snapshot().ply).toBe(0);
    expect(ai.snapshot().phase).toBe('paused');
    ai.dispose();
  });

  it('changing speed preserves an ongoing search, while difficulty changes invalidate it', async () => {
    const { s, ai, client, reply, queue } = setup({ running: true });
    await vi.advanceTimersByTimeAsync(100);
    ai.configure({ ...DEFAULT_AI_OPTIONS, running: true, delayMs: 500 });
    expect(client.cancel).not.toHaveBeenCalled();
    reply(); await vi.advanceTimersByTimeAsync(499);
    expect(client.search).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(queue).toHaveLength(2);
    ai.configure({ ...DEFAULT_AI_OPTIONS, running: true, delayMs: 500, wDifficulty: 'easy' });
    expect(client.cancel).toHaveBeenCalledTimes(1);
    reply(1); await vi.advanceTimersByTimeAsync(500);
    expect(s.snapshot().ply).toBe(1);
    expect(queue[2]!.input.difficulty).toBe('easy');
    ai.dispose();
  });

  it('changing display delay cannot erase an already requested single step', async () => {
    const { s, ai, client, reply } = setup();
    ai.step();
    ai.configure({ ...DEFAULT_AI_OPTIONS, delayMs: 1000 });
    await vi.advanceTimersByTimeAsync(0);
    expect(client.search).toHaveBeenCalledTimes(1);
    reply(); await vi.advanceTimersByTimeAsync(0);
    expect(s.snapshot().ply).toBe(1);
    expect(ai.snapshot().phase).toBe('paused');
    ai.dispose();
  });

  it('position changes invalidate work even when the new game has the same hash', async () => {
    for (const change of ['new', 'goto', 'import', 'resign'] as const) {
      const { s, ai, reply } = setup({ running: true });
      await vi.advanceTimersByTimeAsync(100);
      if (change === 'new') s.newGame();
      if (change === 'goto') s.goto(0);
      if (change === 'import') s.importRecord(s.exportRecord());
      if (change === 'resign') s.resign();
      reply(0); await vi.advanceTimersByTimeAsync(0);
      expect(s.snapshot().ply).toBe(0);
      ai.dispose();
    }
  });

  it('suspension cancels a pending display timer and blocks work until explicitly released', async () => {
    const { ai, client } = setup({ running: true });
    ai.suspend();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(client.search).not.toHaveBeenCalled();
    ai.resume();
    await vi.advanceTimersByTimeAsync(100);
    expect(client.search).toHaveBeenCalledTimes(1);
    ai.dispose();
  });

  it('exposes errors, does not fallback, and retry of a single step stays paused', async () => {
    const { s, ai, client, queue, reply } = setup();
    ai.step(); await vi.advanceTimersByTimeAsync(0);
    queue[0]!.reject(new Error('WASM failed')); await vi.advanceTimersByTimeAsync(0);
    expect(ai.snapshot()).toMatchObject({ phase: 'error', error: 'WASM failed' });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(client.search).toHaveBeenCalledTimes(1);
    ai.retry(); await vi.advanceTimersByTimeAsync(0);
    reply(); await vi.advanceTimersByTimeAsync(0);
    expect(s.snapshot().ply).toBe(1);
    expect(ai.snapshot().phase).toBe('paused');
    ai.dispose();
  });

  it('releasing suspension does not silently retry an errored automatic game', async () => {
    const { ai, client, queue } = setup({ running: true });
    await vi.advanceTimersByTimeAsync(100);
    queue[0]!.reject(new Error('Worker crashed')); await vi.advanceTimersByTimeAsync(0);
    ai.suspend(); ai.resume();
    expect(ai.snapshot()).toMatchObject({ phase: 'error', error: 'Worker crashed' });
    await vi.advanceTimersByTimeAsync(1000);
    expect(client.search).toHaveBeenCalledTimes(1);
    ai.dispose();
  });

  it('human modes only request AI on its side, and finished games cannot step', async () => {
    const black = setup({ mode: 'h-r', running: true });
    await vi.advanceTimersByTimeAsync(1000);
    expect(black.client.search).not.toHaveBeenCalled();
    expect(black.ai.snapshot().phase).toBe('human');
    black.s.play('577567'); await vi.advanceTimersByTimeAsync(100);
    expect(black.queue[0]!.input.side).toBe('w');
    black.ai.dispose();
    const white = setup({ mode: 'r-h', running: true });
    await vi.advanceTimersByTimeAsync(100);
    white.reply(); await vi.advanceTimersByTimeAsync(1000);
    expect(white.client.search).toHaveBeenCalledTimes(1);
    expect(white.ai.snapshot().phase).toBe('human');
    white.s.resign(); white.ai.pause();
    expect(white.ai.step()).toBe(false);
    expect(white.ai.snapshot().phase).toBe('finished');
    white.ai.dispose();
  });

  it('dispose cancels once and a new mounted controller remains usable', async () => {
    const first = setup({ running: true });
    await vi.advanceTimersByTimeAsync(100);
    first.ai.dispose(); first.ai.dispose();
    expect(first.client.dispose).toHaveBeenCalledTimes(1);
    first.reply(); await vi.advanceTimersByTimeAsync(1000);
    expect(first.s.snapshot().ply).toBe(0);
    const second = setup({ running: true });
    await vi.advanceTimersByTimeAsync(100);
    second.reply(); await vi.advanceTimersByTimeAsync(0);
    expect(second.s.snapshot().ply).toBe(1);
    second.ai.dispose();
  });
});
