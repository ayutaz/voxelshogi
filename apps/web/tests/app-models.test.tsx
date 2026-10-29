// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { releaseFixture, trainedFixture } from './local-model-fixtures';
import type { ArenaOptions } from '../src/ai/arena-controller';
const fake = vi.hoisted(() => ({ configure: vi.fn(), pause: vi.fn() }));
vi.mock('../src/game/store', () => {
  const snap = { side: 'b', ply: 0, moveCount: 0, finished: false, inCheck: { b: false, w: false }, legal: [], board: [] };
  return { MAX_IMPORT_BYTES: 4e6, GameStore: class { subscribe = () => () => {}; snapshot = () => snap; exportRecord = () => JSON.stringify({ initial: 'fixture', ruleset_id: 'voxelshogi-standard-v1', moves: [] }); } };
});
vi.mock('../src/ai/arena-controller', async original => ({ ...await original<object>(), ArenaController: class {
  subscribe = () => () => {}; snapshot = () => ({ phase: 'paused', error: null, last: null });
  configure = fake.configure; pause = fake.pause; resume = () => {}; dispose = () => {};
  journal = { snapshot: () => [] };
} }));
vi.mock('../src/components/Board2D', () => ({ Board2D: () => null }));
vi.mock('../src/components/Panels', () => ({ Hands: () => null, MoveList: () => null, PromotionDialog: () => null, resultText: () => '' }));
vi.mock('../src/inference/ModelLibraryPanel', () => ({ default: ({ onLoaded }: { onLoaded: (value: unknown) => void }) => <button onClick={() => onLoaded({ release: releaseFixture(), model: trainedFixture(), files: [] })}>fixture folder</button> }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
const options = () => fake.configure.mock.calls.at(-1)![0] as ArenaOptions;
it.each(['b', 'w'] as const)('preserves the %s Easy seat when an inactive previously used model is removed', async side => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: '学習済みモデルを読み込む' }));
  fireEvent.click(await screen.findByRole('button', { name: 'fixture folder' }));
  fireEvent.change(screen.getByTestId(`difficulty-${side}`), { target: { value: 'model' } });
  fireEvent.change(screen.getByTestId(`difficulty-${side}`), { target: { value: 'easy' } });
  fireEvent.click(screen.getByRole('button', { name: 'モデルを外す' }));
  expect(options()[side === 'b' ? 'bDifficulty' : 'wDifficulty']).toBe('easy');
  expect(options()[side === 'b' ? 'wDifficulty' : 'bDifficulty']).toBe('normal');
  expect(options()[side === 'b' ? 'bModel' : 'wModel']).toBeUndefined();
  expect(options().running).toBe(false);
});
it('selects each seat, pauses on changes, and removes an active source explicitly', async () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: '学習済みモデルを読み込む' }));
  fireEvent.click(await screen.findByRole('button', { name: 'fixture folder' }));
  fireEvent.change(screen.getByTestId('difficulty-b'), { target: { value: 'model' } });
  await waitFor(() => expect(options().bDifficulty).toBe('model'));
  expect(options().bModel!.selection.precision).toBe('fp32');
  fireEvent.change(screen.getByTestId('backend-b'), { target: { value: 'webgpu' } });
  expect(options().bModel!.selection.backend).toBe('webgpu');
  expect(options().wDifficulty).toBe('normal');
  expect(options().running).toBe(false);
  const oldSource = options().bModel!.sourceId;
  fireEvent.click(screen.getByRole('button', { name: 'fixture folder' }));
  expect(options().bModel!.sourceId).not.toBe(oldSource);
  expect(options().bModel!.selection.backend).toBe('webgpu');
  fireEvent.click(screen.getByRole('button', { name: 'モデルを外す' }));
  expect(options().bDifficulty).toBe('normal');
  expect(options().bModel).toBeUndefined();
  expect(fake.pause).toHaveBeenCalled();
});
it('freezes selected AI conditions before build-info loading and exports the actual commit', async () => {
  let finish!: (value: unknown) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve; })));
  const create = vi.fn<(blob: Blob) => string>(() => 'blob:record');
  vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(<App />);
  fireEvent.click(screen.getByTestId('export-ai-record'));
  fireEvent.change(screen.getByTestId('thinking-budget'), { target: { value: '100' } });
  finish({ ok: true, json: async () => ({ commit: 'a'.repeat(40) }) });
  await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
  const text = await new Promise<string>(resolve => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(create.mock.calls[0]![0]);
  });
  expect(JSON.parse(text)).toMatchObject({ applicationCommit: 'a'.repeat(40), selectedAgents: { b: { limits: { maxTimeMs: 1000 } } }, observationsThroughCursor: [], record: { moves: [] } });
  expect(options().limits.maxTimeMs).toBe(100);
});
