// Pure fake ports; no ONNX runtime, model execution or Rust search on Mac.
import { expect, it, vi } from 'vitest';
import { PolicySession, type PolicySelection } from '../src/inference/policy-session';
import type { BackendPort, Profile } from '../src/inference/backend';
import { parseTrainedCatalog, type LocalModel } from '../src/inference/local-model';
import { POLICY_ELEMENTS, parseTrainedModel } from '../src/inference/manifest';
import { releaseFixture, trainedFixture } from './local-model-fixtures';

const selection = (): PolicySelection => ({ modelId: 'voxelshogi-transformer-s-m6-314159-v1', packageHash: 'a'.repeat(64), precision: 'fp32', backend: 'wasm' });
const root = () => ({ revision: 7, cursor: 3, side: 'b', hash: '1'.repeat(16), ruleset: 'voxelshogi-standard-v1',
  recordJson: JSON.stringify({ side: 'b', hash: '1'.repeat(16), moves: ['111211', '999899', '211311'] }) });

function setup() {
  const policy = new Float32Array(POLICY_ELEMENTS), value = new Float32Array([.25]);
  const input = new Float32Array(729 * 43);
  for (let cell = 0; cell < 729; cell++) input[cell * 43] = 1; // Independent empty-board oracle.
  const outputDispose = vi.fn();
  const session = { run: vi.fn(async () => ({ policy, value, dispose: outputDispose })), finishProfiling: vi.fn(async () => {}), release: vi.fn(async () => {}) };
  const port: BackendPort = { createSession: vi.fn(async () => session), dispose: vi.fn(async () => {}), resetProfile: vi.fn(),
    profile: vi.fn(() => ({ providers: { CPUExecutionProvider: 1 }, operators: { MatMul: 1 } })),
    info: { backend: 'wasm', adapter: null, features: [], runtimeBytes: 100 } };
  const release = parseTrainedCatalog({ schema: 1, releases: [releaseFixture()] })[0]!;
  const model = parseTrainedModel(trainedFixture(), release), first = model.fixtures[0]!;
  model.fixtures.push({ ...first, name: 'empty-w', side: 'w', input: { ...first.input, path: 'inputs/white.f32' } });
  model.variants[0]!.references['empty-w'] = { policy: { ...model.variants[0]!.references['initial-b']!.policy, path: 'reference/white-policy.f32' }, value: { ...model.variants[0]!.references['initial-b']!.value, path: 'reference/white-value.f32' } };
  Reflect.set(model.fixtures[0]!.record, 'side', 'b');
  model.fixtures[1]!.record = { ruleset_id: 'voxelshogi-standard-v1', side: 'w' };
  const source: LocalModel = { release, model, packageHash: 'a'.repeat(64),
    read: vi.fn(async file => file.path.endsWith('.onnx') ? new Uint8Array(3) : file.path.startsWith('inputs/') ? new Uint8Array(input.buffer) : file.path.includes('policy') ? new Uint8Array(policy.buffer) : new Uint8Array(value.buffer)) };
  const games: { goto: ReturnType<typeof vi.fn>; free: ReturnType<typeof vi.fn>; board: ReturnType<typeof vi.fn>; legalMoves: ReturnType<typeof vi.fn> }[] = [];
  const game = vi.fn((recordJson: string) => {
    const record = JSON.parse(recordJson); let cursor = 0;
    const result = { goto: vi.fn((ply: number) => { cursor = ply; }), ply: () => cursor, sideToMove: () => record.side,
      hash: () => record.hash ?? '1'.repeat(16), isFinished: () => record.finished === true,
      board: vi.fn(() => new Uint8Array(729)), hands: () => new Uint8Array(14), legalMoves: vi.fn(() => ['211111', '111211']), free: vi.fn() };
    games.push(result); return result;
  });
  const open = vi.fn(async () => port);
  return { engine: new PolicySession({ source, open, game, now: () => performance.now() }), source, open, port, session, policy, value, input, game, games, outputDispose };
}

it('validates every fixture with one exact-precision session before permitting moves', async () => {
  const f = setup(), ready = await f.engine.initialize(selection());
  expect(ready.selection).toEqual(selection());
  expect(ready.fixtures.map(row => row.name)).toEqual(['initial-b', 'empty-w']);
  expect(ready.fixtures.every(row => row.comparison.policy.elements === POLICY_ELEMENTS && row.comparison.policy.exceeded === 0)).toBe(true);
  expect(f.open).toHaveBeenCalledWith('wasm', 'fp32');
  expect(f.port.createSession).toHaveBeenCalledWith(expect.any(Uint8Array), 'fp32');
  expect(f.session.run).toHaveBeenCalledTimes(2); expect(f.outputDispose).toHaveBeenCalledTimes(2);
  expect(f.games.every(game => game.free.mock.calls.length === 1)).toBe(true);
  expect(f.session.release).not.toHaveBeenCalled();
  await f.engine.dispose(); await f.engine.dispose();
  expect(f.session.release).toHaveBeenCalledTimes(1); expect(f.port.dispose).toHaveBeenCalledTimes(1);
});

it('replays full history at the requested cursor, then chooses a canonical legal move', async () => {
  const f = setup(); await f.engine.initialize(selection());
  const scores = new Float32Array(POLICY_ELEMENTS); scores[0] = 1000;
  f.session.run.mockResolvedValue({ policy: scores, value: f.value, dispose: f.outputDispose });
  const result = await f.engine.bestMove(root());
  expect(result.root).toEqual({ revision: 7, cursor: 3, side: 'b', hash: '1'.repeat(16), ruleset: 'voxelshogi-standard-v1' });
  expect(result.selection).toEqual(selection());
  expect(result.choice).toEqual({ move: '111211', action: 2, value: .25, rawAction: 0, rawLegal: false });
  expect(result.finished).toBe(false);
  expect(f.game).toHaveBeenLastCalledWith(root().recordJson);
  expect(f.games.at(-1)!.goto).toHaveBeenCalledWith(3); expect(f.games.at(-1)!.free).toHaveBeenCalledTimes(1);
  expect(f.session.run).toHaveBeenCalledTimes(3); expect(f.session.release).not.toHaveBeenCalled();
  await f.engine.dispose();
});

it('flushes native profiling after all fixtures and keeps that verified session for play', async () => {
  const f = setup(); let flushed = false;
  f.session.finishProfiling.mockImplementation(async () => {
    expect(f.session.run).toHaveBeenCalledTimes(2); flushed = true;
  });
  vi.mocked(f.port.profile).mockImplementation((): Profile => flushed
    ? { providers: { CPUExecutionProvider: 12 }, operators: { MatMul: 12 } }
    : { providers: {}, operators: {} });
  const pending = f.engine.initialize(selection());
  await expect(pending).resolves.toMatchObject({ profile: { providers: { CPUExecutionProvider: 12 } } });
  const validation = await pending;
  expect(validation.profile.providers).toEqual({ CPUExecutionProvider: 12 });
  expect(f.session.finishProfiling).toHaveBeenCalledTimes(1);
  await f.engine.bestMove(root());
  expect(f.port.createSession).toHaveBeenCalledTimes(1);
  expect(f.session.release).not.toHaveBeenCalled();
  await f.engine.dispose();
});

it('refuses a model/backend/format mismatch without fallback or backend initialization', async () => {
  for (const change of [{ modelId: 'other' }, { packageHash: 'b'.repeat(64) }, { precision: 'int8' }, { backend: 'other' }]) {
    const f = setup();
    await expect(f.engine.initialize({ ...selection(), ...change })).rejects.toThrow();
    expect(f.open).not.toHaveBeenCalled(); expect(f.source.read).not.toHaveBeenCalled();
  }
  const f = setup(); f.source.model.trained = false;
  await expect(f.engine.initialize(selection())).rejects.toThrow(/trained/);
  expect(f.open).not.toHaveBeenCalled();
});

it('opens each available reduced-precision file using its selected session precision', async () => {
  for (const precision of ['fp16', 'int8'] as const) {
    const f = setup(), variant = f.source.model.variants[0]!;
    f.source.model.variants.push({ ...variant, id: precision, precision, model: { ...variant.model, path: `${precision}.onnx` } });
    await f.engine.initialize({ ...selection(), precision });
    expect(f.open).toHaveBeenCalledWith('wasm', precision);
    expect(f.port.createSession).toHaveBeenCalledWith(expect.any(Uint8Array), precision);
    expect(f.source.read).toHaveBeenCalledWith(expect.objectContaining({ path: `${precision}.onnx` }));
    await f.engine.dispose();
  }
});

it('rejects reference input divergence at the last element before running a session', async () => {
  const f = setup(), read = f.source.read;
  f.source.read = async file => {
    if (!file.path.startsWith('inputs/')) return read(file);
    const bad = f.input.slice(); bad[bad.length - 1] = 1; return new Uint8Array(bad.buffer);
  };
  await expect(f.engine.initialize(selection())).rejects.toThrow(/input/);
  expect(f.session.run).not.toHaveBeenCalled();
  expect(f.games[0]!.free).toHaveBeenCalledTimes(1);
  expect(f.session.release).toHaveBeenCalledTimes(1); expect(f.port.dispose).toHaveBeenCalledTimes(1);
});

it('rejects a last-element numeric mismatch and frees all outputs/session/backend', async () => {
  const f = setup(), bad = f.policy.slice(); bad[POLICY_ELEMENTS - 1] = 1;
  f.session.run.mockResolvedValue({ policy: bad, value: f.value, dispose: f.outputDispose });
  await expect(f.engine.initialize(selection())).rejects.toThrow(/tolerance/);
  expect(f.outputDispose).toHaveBeenCalledTimes(1);
  expect(f.session.release).toHaveBeenCalledTimes(1); expect(f.port.dispose).toHaveBeenCalledTimes(1);
});

it('uses the trained Policy bound for reference runs and retains the tighter Value bound', async () => {
  const f = setup(), roundoff = f.policy.slice(); roundoff[POLICY_ELEMENTS - 1] = .00009;
  f.session.run.mockResolvedValue({ policy: roundoff, value: f.value, dispose: f.outputDispose });
  const ready = await f.engine.initialize(selection());
  expect(ready.fixtures[0]!.comparison.policy.atol).toBe(.0001);
  expect(ready.fixtures[0]!.comparison.value.atol).toBe(.00001);
  await f.engine.dispose();
  const g = setup();
  g.session.run.mockResolvedValue({ policy: g.policy, value: new Float32Array([.25009]), dispose: g.outputDispose });
  await expect(g.engine.initialize(selection())).rejects.toThrow(/tolerance/);
  expect(g.port.dispose).toHaveBeenCalledTimes(1);
});

it('rejects absent or unknown trained numeric contracts before reading or opening a model', async () => {
  for (const marker of [undefined, 'unknown']) {
    const f = setup(); Reflect.set(f.source.model, 'numericContract', marker);
    await expect(f.engine.initialize(selection())).rejects.toThrow(/numeric/);
    expect(f.source.read).not.toHaveBeenCalled(); expect(f.open).not.toHaveBeenCalled();
  }
});

it('does not accept a different provider or relabel a CPU backend as WebGPU', async () => {
  const f = setup();
  await expect(f.engine.initialize({ ...selection(), backend: 'webgpu' })).rejects.toThrow(/backend|placement/);
  expect(f.port.dispose).toHaveBeenCalledTimes(1);
});

it('does not run the model at a terminal position and always frees its Rust game', async () => {
  const f = setup(); await f.engine.initialize(selection());
  const result = await f.engine.bestMove({ ...root(), recordJson: JSON.stringify({ side: 'b', hash: '1'.repeat(16), finished: true }) });
  expect(result.choice).toBeNull(); expect(result.finished).toBe(true);
  expect(f.session.run).toHaveBeenCalledTimes(2);
  const game = f.games.at(-1)!;
  expect(game.legalMoves).not.toHaveBeenCalled(); expect(game.board).not.toHaveBeenCalled(); expect(game.free).toHaveBeenCalledTimes(1);
  await f.engine.dispose();
});

it('rejects stale roots and malformed metadata before performing inference', async () => {
  const f = setup(); await f.engine.initialize(selection());
  for (const change of [{ hash: '2'.repeat(16) }, { side: 'w' }, { cursor: -1 }, { revision: 1.5 }, { ruleset: 'other' }, { recordJson: '' }])
    await expect(f.engine.bestMove({ ...root(), ...change })).rejects.toThrow();
  expect(f.session.run).toHaveBeenCalledTimes(2);
  expect(f.games.every(game => game.free.mock.calls.length === 1)).toBe(true);
  await f.engine.dispose();
});

it('rejects calls before validation and requires a new session for model/backend changes', async () => {
  const f = setup(); await expect(f.engine.bestMove(root())).rejects.toThrow(/ready|initial/);
  await f.engine.initialize(selection());
  await expect(f.engine.initialize({ ...selection(), backend: 'webgpu' })).rejects.toThrow();
  expect(f.open).toHaveBeenCalledTimes(1); await f.engine.dispose();
});

it('cancels an in-flight move without applying a stale result or leaking resources', async () => {
  const f = setup(); await f.engine.initialize(selection());
  let finish!: (output: Awaited<ReturnType<typeof f.session.run>>) => void;
  f.session.run.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = f.engine.bestMove(root());
  await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
  await expect(f.engine.bestMove(root())).rejects.toThrow(/busy/);
  await f.engine.dispose();
  finish({ policy: f.policy, value: f.value, dispose: f.outputDispose });
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  expect(f.outputDispose).toHaveBeenCalledTimes(3);
  expect(f.session.release).toHaveBeenCalledTimes(1); expect(f.port.dispose).toHaveBeenCalledTimes(1);
});

it('releases a failed inference session and does not retry or substitute another backend', async () => {
  for (const synchronous of [false, true]) {
    const f = setup(); await f.engine.initialize(selection());
    if (synchronous) f.session.run.mockImplementationOnce(() => { throw new Error('backend execution failed'); });
    else f.session.run.mockRejectedValueOnce(new Error('backend execution failed'));
    await expect(f.engine.bestMove(root())).rejects.toThrow('backend execution failed');
    expect(f.session.release).toHaveBeenCalledTimes(1); expect(f.port.dispose).toHaveBeenCalledTimes(1);
    expect(f.games.at(-1)!.free).toHaveBeenCalledTimes(1);
    await expect(f.engine.bestMove(root())).rejects.toMatchObject({ name: 'AbortError' });
    expect(f.session.run).toHaveBeenCalledTimes(3); expect(f.open).toHaveBeenCalledTimes(1);
  }
});

it('cancels during session creation and releases the late session without running it', async () => {
  const f = setup();
  let finish!: (value: Awaited<ReturnType<typeof f.port.createSession>>) => void;
  vi.mocked(f.port.createSession).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = f.engine.initialize(selection());
  await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
  await f.engine.dispose(); finish(f.session);
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  expect(f.session.run).not.toHaveBeenCalled();
  expect(f.session.release).toHaveBeenCalledTimes(1); expect(f.port.dispose).toHaveBeenCalledTimes(1);
});
