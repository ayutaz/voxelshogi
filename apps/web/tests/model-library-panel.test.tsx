// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { LocalModel } from '../src/inference/local-model';
import ModelLibraryPanel from '../src/inference/ModelLibraryPanel';
import { releaseFixture, trainedFixture } from './local-model-fixtures';

const fake = vi.hoisted(() => ({ catalog: vi.fn(), load: vi.fn(), pack: vi.fn() }));
vi.mock('../src/inference/local-model', async importOriginal => ({ ...await importOriginal<object>(), readTrainedCatalog: fake.catalog, loadLocalModel: fake.load }));
vi.mock('../src/inference/policy-protocol', () => ({ packModelFiles: fake.pack, localFile: (value: unknown) => value }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
async function mount() {
  fake.catalog.mockResolvedValue({ schema: 1, releases: [releaseFixture()] });
  const loaded = vi.fn(); render(<ModelLibraryPanel onLoaded={loaded} />);
  await screen.findByTestId('model-folder');
  return loaded;
}
it('explains empty releases and links to the fixed HF revision without downloading weights', async () => {
  fake.catalog.mockResolvedValue({ schema: 1, releases: [] });
  render(<ModelLibraryPanel onLoaded={vi.fn()} />);
  await screen.findByText(/公開済みの学習モデルはまだありません/);
  expect(screen.queryByTestId('model-folder')).toBeNull();
  cleanup(); await mount();
  expect(screen.getByRole('link', { name: 'Hugging Faceで取得' }).getAttribute('href')).toBe(`https://huggingface.co/voxelshogi/voxelshogi-transformer-s/tree/${'f'.repeat(40)}`);
  expect(fake.load).not.toHaveBeenCalled();
});
it('does not publish a late folder completion after another selection or unmount', async () => {
  const loaded = await mount();
  let late!: (value: LocalModel) => void;
  fake.pack.mockReturnValue([]);
  fake.load.mockImplementationOnce(() => new Promise(resolve => { late = resolve; }));
  const input = screen.getByTestId('model-folder');
  fireEvent.change(input, { target: { files: [new File(['a'], 'manifest.json')] } });
  const firstSignal = fake.load.mock.calls[0]![2] as AbortSignal;
  fake.load.mockResolvedValueOnce({ release: releaseFixture(), model: trainedFixture() });
  fireEvent.change(input, { target: { files: [new File(['b'], 'manifest.json')] } });
  await screen.findByText(/AI開始時に/);
  expect(firstSignal.aborted).toBe(true);
  expect(loaded).toHaveBeenCalledTimes(1);
  await act(async () => late({ release: releaseFixture(), model: trainedFixture() } as unknown as LocalModel));
  expect(loaded).toHaveBeenCalledTimes(1);
  cleanup();
  expect((fake.load.mock.calls[1]![2] as AbortSignal).aborted).toBe(true);
});
it('shows failed validation and allows retrying without changing the approved release', async () => {
  const loaded = await mount(); fake.pack.mockReturnValue([]); fake.load.mockRejectedValueOnce(new Error('hash mismatch'));
  fireEvent.change(screen.getByTestId('model-folder'), { target: { files: [new File(['x'], 'manifest.json')] } });
  expect((await screen.findByRole('alert')).textContent).toContain('hash mismatch');
  expect(loaded).not.toHaveBeenCalled();
});
it('rejects a queued successful folder read after the panel is closed', async () => {
  const loaded = await mount();
  let finish!: (value: unknown) => void;
  fake.pack.mockReturnValue([]); fake.load.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  fireEvent.change(screen.getByTestId('model-folder'), { target: { files: [new File(['a'], 'manifest.json')] } });
  const signal = fake.load.mock.calls[0]![2] as AbortSignal;
  cleanup();
  expect(signal.aborted).toBe(true);
  await act(async () => finish({ release: releaseFixture(), model: trainedFixture() }));
  expect(loaded).not.toHaveBeenCalled();
});
