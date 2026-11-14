// @vitest-environment jsdom
import { act as __publicAct, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { releaseFixture, trainedFixture } from './local-model-fixtures';
import type { ArenaOptions } from '../src/ai/arena-controller';
const fake = vi.hoisted(() => ({ configure: vi.fn(), pause: vi.fn(), publicModel: vi.fn() }));
vi.mock('../src/inference/public-model', () => ({ preparePublicModel: fake.publicModel }));
vi.mock('../src/game/store', () => {
  const snap = { side: 'b', ply: 0, moveCount: 0, finished: false, inCheck: { b: false, w: false }, legal: [], board: [] };
  return { MAX_IMPORT_BYTES: 4e6, GameStore: class { subscribePresentation = () => () => {}; stepForward = () => {}; newGame = () => {}; subscribe = () => () => {}; snapshot = () => snap; exportRecord = () => JSON.stringify({ initial: 'fixture', ruleset_id: 'voxelshogi-standard-v1', moves: [] }); } };
});
vi.mock('../src/ai/arena-controller', async original => ({ ...await original<object>(), ArenaController: class {
  subscribe = () => () => {}; snapshot = () => ({ phase: 'paused', error: null, last: null });
  configure = fake.configure; pause = fake.pause; resume = () => {}; dispose = () => {};
  journal = { snapshot: () => [],clear:()=>{} };
} }));
vi.mock('../src/renderer/Board3D', () => ({ Board3D: () => null }));
vi.mock('../src/components/Board2D', () => ({ Board2D: () => null }));
vi.mock('../src/components/Panels', () => ({ Hands: () => null, MoveList: () => null, PromotionDialog: () => null, resultText: () => '' }));
vi.mock('../src/inference/ModelLibraryPanel', () => ({ default: ({ onLoaded }: { onLoaded: (value: unknown) => void }) => <button onClick={() => onLoaded({ release: releaseFixture(), model: trainedFixture(), files: [] })}>fixture folder</button> }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
beforeEach(() => { fake.publicModel.mockRejectedValue(new Error('no public fixture requested')); });
const options = () => fake.configure.mock.calls.at(-1)![0] as ArenaOptions;
it('starts a public S match without a folder and keeps the chosen precision', async () => {
  const model = trainedFixture(); model.variants.push({ ...model.variants[0]!, id: 'int8', precision: 'int8' });
  fake.publicModel.mockResolvedValue({ release: { ...releaseFixture(), publicDownload: true }, model, files: [] });
  render(<App />); fireEvent.click(screen.getByRole('button', { name: 'AIと対戦' }));
  fireEvent.change(screen.getByLabelText('相手のAI'), { target: { value: 'model' } });
  await waitFor(() => expect(fake.publicModel).toHaveBeenCalledTimes(1));
  await screen.findByLabelText('モデルの精度形式');
  fireEvent.change(screen.getByLabelText('モデルの精度形式'), { target: { value: 'int8' } });
  fireEvent.click(screen.getByRole('button', { name: '対戦をはじめる' }));
  expect(options()).toMatchObject({ mode: 'h-r', running: true, wDifficulty: 'model', wModel: { files: [], selection: { precision: 'int8', backend: 'wasm' } } });
});
it('ignores public metadata that finishes after the match sheet is closed', async () => {
  let finish!: (packet: unknown) => void;
  fake.publicModel.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<App />); fireEvent.click(screen.getByRole('button', { name: 'AIと対戦' }));
  fireEvent.change(screen.getByLabelText('相手のAI'), { target: { value: 'model' } });
  await waitFor(() => expect(fake.publicModel).toHaveBeenCalledTimes(1));
  const signal = fake.publicModel.mock.calls[0]![0] as AbortSignal;
  fireEvent.click(screen.getByRole('button', { name: '閉じる' }));
  expect(signal.aborted).toBe(true);
  await __publicAct(async () => finish({ release: releaseFixture(), model: trainedFixture(), files: [] }));
  expect(options().wModel).toBeUndefined(); expect(options().running).toBe(false);
  expect(document.querySelectorAll('.model-source')).toHaveLength(0);
});
it('assigns an actual loaded model when the human entry selects S for the first time', async () => {
  render(<App />);fireEvent.click(screen.getByRole('button',{name:'モデル'}));
  fireEvent.click(screen.getByRole('button',{name:'学習済みモデルを読み込む'}));fireEvent.click(await screen.findByRole('button',{name:'fixture folder'}));
  fireEvent.click(screen.getByRole('button',{name:'閉じる'}));fireEvent.click(screen.getByRole('button',{name:'AIと対戦'}));
  fireEvent.change(screen.getByLabelText('相手のAI'),{target:{value:'model'}});fireEvent.click(screen.getByRole('button',{name:'対戦をはじめる'}));
  expect(options()).toMatchObject({mode:'h-r',running:true,wDifficulty:'model'});
  expect(options().wModel?.selection.modelId).toBe(releaseFixture().id);
});
it.each(['b', 'w'] as const)('preserves the %s Easy seat when an inactive previously used model is removed', async side => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'モデル' }));
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
  fireEvent.click(screen.getByRole('button', { name: 'モデル' }));
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
