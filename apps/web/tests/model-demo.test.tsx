// @vitest-environment jsdom
// UI control tests use fake clients; real Worker/backend tests run in Chrome.
import { StrictMode } from 'react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { loadWasm } from './loadWasm';
import { modelFixture, deploymentFixture } from './inference-fixtures';
import type { ClientResult, InferenceInput, Phase } from '../src/inference/client';
import type { ModelPackage } from '../src/inference/runtime';
import { parseModel } from '../src/inference/manifest';
import ModelDemo from '../src/inference/ModelDemo';

const fake = vi.hoisted(() => ({ load: vi.fn(), clients: [] as { infer: ReturnType<typeof vi.fn>; cancel: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn> }[] }));
vi.mock('../src/inference/runtime', () => ({ loadPackage: fake.load }));
vi.mock('../src/inference/client', () => ({ InferenceClient: class {
  infer = vi.fn(); cancel = vi.fn(); dispose = vi.fn();
  constructor() { fake.clients.push(this); }
} }));
vi.mock('../src/renderer/Board3D', () => ({ Board3D: () => <div data-testid="demo-board3d" /> }));
beforeAll(loadWasm);
beforeEach(() => { fake.clients.length = 0; fake.load.mockReset(); });
afterEach(cleanup);
function pkg() {
  const model = parseModel(modelFixture());
  const positions = JSON.parse(readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../export/fixtures/positions.json'), 'utf8')) as { name: string; record: Record<string, unknown> }[];
  const first = model.fixtures[0]!;
  model.fixtures = positions.slice(0, 2).map((p) => ({ ...first, name: p.name, record: p.record }));
  const base = model.variants[0]!;
  const references = Object.fromEntries(model.fixtures.map(f => [f.name, base.references['initial-b']!]));
  model.variants = (['fp32', 'fp16', 'int8'] as const).map(id => ({ ...base, id, precision: id, references }));
  return { model, index: deploymentFixture(), packageHash: 'a'.repeat(64), assetBase: 'https://example.test/models/m3/', modelBase: 'https://example.test/models/m3/models/hash/' } as unknown as ModelPackage;
}
async function mount() {
  fake.load.mockResolvedValue(pkg());
  render(<StrictMode><ModelDemo /></StrictMode>);
  await screen.findByRole('button', { name: '推論を実行' });
  return fake.clients.at(-1)!;
}

it('shows the untrained model and every executable precision, with no claim of playing strength', async () => {
  await mount();
  expect(screen.getByText(/未学習モデル/)).toBeTruthy();
  const precision = screen.getByLabelText('精度形式');
  expect(precision.querySelectorAll('option')).toHaveLength(3);
  expect(precision.textContent).toContain('INT8（重み）');
  expect(screen.getByTestId('model-hash').textContent).toBe('a'.repeat(64));
  expect(screen.getByRole('link', { name: 'モデルのライセンス' }).getAttribute('href')).toBe('https://example.test/models/m3/models/hash/LICENSE.txt');
  expect(screen.getByRole('link', { name: 'Model Card' }).getAttribute('href')).toBe('https://example.test/models/m3/models/hash/MODEL_CARD.md');
  expect(screen.getByTestId('fixture-side').textContent).toContain('先手');
  fireEvent.change(screen.getByLabelText('検証局面'), { target: { value: 'after-one-w' } });
  expect(screen.getByTestId('fixture-side').textContent).toContain('後手');
});

it('cancels on a root change and rejects a queued old success/progress before a fresh retry', async () => {
  const client = await mount();
  let late!: (result: ClientResult) => void, progress!: (phase: Phase, at: number) => void;
  client.infer.mockImplementationOnce((_input: InferenceInput, onProgress: typeof progress) => {
    progress = onProgress; return new Promise(resolve => { late = resolve; });
  });
  fireEvent.click(screen.getByRole('button', { name: '推論を実行' }));
  act(() => progress('running', 100));
  expect(screen.getByTestId('inference-phase').getAttribute('data-phase')).toBe('running');
  fireEvent.change(screen.getByLabelText('精度形式'), { target: { value: 'int8' } });
  expect(client.cancel).toHaveBeenCalled();
  await act(async () => { progress('running', 101); late({ value: 0.99 } as ClientResult); });
  expect(screen.queryByTestId('inference-result')).toBeNull();
  expect(screen.getByTestId('inference-phase').getAttribute('data-phase')).toBe('idle');
  client.infer.mockRejectedValueOnce(new Error('WebGPU unavailable'));
  fireEvent.click(screen.getByRole('button', { name: '推論を実行' }));
  expect((client.infer.mock.calls.at(-1)![0] as InferenceInput).variant).toBe('int8');
  await screen.findByRole('alert');
  expect(screen.getByRole('button', { name: '推論を実行' }).hasAttribute('disabled')).toBe(false);
});

it('allows cancellation, retries a failed manifest load, and releases StrictMode clients', async () => {
  fake.load.mockRejectedValue(new Error('package missing'));
  const mounted = render(<StrictMode><ModelDemo /></StrictMode>);
  await screen.findByRole('alert');
  fake.load.mockResolvedValue(pkg());
  fireEvent.click(screen.getByRole('button', { name: '読み込みを再試行' }));
  await screen.findByRole('button', { name: '推論を実行' });
  const client = fake.clients.at(-1)!;
  client.infer.mockImplementation(() => new Promise(() => {}));
  fireEvent.click(screen.getByRole('button', { name: '30回を計測' }));
  expect((client.infer.mock.calls[0]![0] as InferenceInput).iterations).toBe(40);
  fireEvent.click(screen.getByRole('button', { name: '中断' }));
  expect(client.cancel).toHaveBeenCalled();
  expect(screen.getByTestId('inference-phase').getAttribute('data-phase')).toBe('cancelled');
  mounted.unmount();
  expect(fake.clients.every(c => c.dispose.mock.calls.length === 1)).toBe(true);
});
