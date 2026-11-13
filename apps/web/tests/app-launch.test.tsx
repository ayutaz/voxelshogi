// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import type { Snapshot } from '../src/game/store';

const fake = vi.hoisted(() => ({ snap: {} as Snapshot, listeners: new Set<() => void>(), reset: vi.fn(), imported: vi.fn(), configure: vi.fn() }));
vi.mock('../src/game/store', () => ({ MAX_IMPORT_BYTES: 4e6, GameStore: class {
  subscribe = (fn: () => void) => { fake.listeners.add(fn); return () => fake.listeners.delete(fn); };
  snapshot = () => fake.snap;
  newGame = fake.reset;
  importRecord = fake.imported;
} }));
vi.mock('../src/ai/arena-controller', () => ({ DEFAULT_AI_OPTIONS: { limits: {} }, ArenaController: class {
  subscribe = () => () => {}; snapshot = () => ({ phase: 'paused', error: null, last: null });
  configure = fake.configure; pause = () => {}; resume = () => {}; suspend = () => {}; dispose = () => {};
  journal = { clear: () => {} };
} }));
vi.mock('../src/renderer/Board3D', () => ({ Board3D: () => <div data-testid="fake-3d" /> }));
beforeEach(() => {
  fake.snap = { revision: 0, side: 'b', ply: 0, moveCount: 0, moves: [], finished: false, result: null,
    lastMove: null, legal: [], board: new Uint8Array(729), hands: new Uint8Array(14),
    inCheck: { b: false, w: false }, kingSquare: { b: 0, w: 728 }, hash: '0000000000000000' };
  fake.imported.mockReturnValue({ ok: true });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });
function moves() {
  act(() => {
    fake.snap = { ...fake.snap, revision: 1, ply: 1, moveCount: 1, moves: ['575566'], lastMove: '575566', side: 'w' };
    for (const fn of fake.listeners) fn();
  });
}

it('offers model-free viewing beside the board and explains the rules', () => {
  const { container } = render(<App />);
  expect(screen.getByTestId('toggle-run').textContent).toBe('観戦を開始');
  expect(container.querySelector('main [data-testid="toggle-run"]')).not.toBeNull();
  expect(screen.getByText(/相手の玉を詰ませると勝ち/)).toBeTruthy();
  fireEvent.click(screen.getByTestId('toggle-run'));
  expect(screen.getByTestId('toggle-run').textContent).toBe('一時停止');
  expect(fake.configure.mock.calls.at(-1)![0]).toMatchObject({ running: true, bDifficulty: 'normal', wDifficulty: 'normal' });
  fireEvent.click(screen.getByTestId('toggle-run'));
  expect(screen.getByTestId('toggle-run').textContent).toBe('観戦を開始');
});

it('shows the current move and follows its destination, including undo to the start', () => {
  render(<App />); moves();
  expect(screen.getByTestId('last-move').textContent).toContain('5七V→5六VI');
  expect(screen.getByRole('slider', { name: /位置/ }).getAttribute('value')).toBe('5');
  fireEvent.change(screen.getByTestId('slice-index'), { target: { value: '1' } });
  expect((screen.getByTestId('follow-move') as HTMLInputElement).checked).toBe(false);
  expect(screen.getByRole('slider', { name: /位置/ }).getAttribute('value')).toBe('1');
  fireEvent.click(screen.getByTestId('follow-move'));
  expect(screen.getByRole('slider', { name: /位置/ }).getAttribute('value')).toBe('5');
  act(() => { fake.snap = { ...fake.snap, ply: 0, lastMove: null }; for (const fn of fake.listeners) fn(); });
  expect(screen.getByTestId('last-move').textContent).not.toContain('5六VI');
});

it('undo and redo follow only the cursor move even when a future move remains in the record', () => {
  render(<App />); moves();
  act(() => {
    fake.snap = { ...fake.snap, ply: 1, moveCount: 2, moves: ['575566', '535544'], lastMove: '575566' };
    for (const fn of fake.listeners) fn();
  });
  expect(screen.getByTestId('last-move').textContent).toContain('先手 5七V→5六VI');
  expect((screen.getByTestId('slice-index') as HTMLInputElement).value).toBe('5');
  act(() => {
    fake.snap = { ...fake.snap, ply: 2, lastMove: '535544' };
    for (const fn of fake.listeners) fn();
  });
  expect(screen.getByTestId('last-move').textContent).toContain('後手 5三V→5四IV');
  expect((screen.getByTestId('slice-index') as HTMLInputElement).value).toBe('3');
});

it.each(['new', 'mode', 'import'])('preserves the game when %s replacement is cancelled', async action => {
  render(<App />); moves();
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  if (action === 'new') fireEvent.click(screen.getByRole('button', { name: '新規対局' }));
  if (action === 'mode') fireEvent.change(screen.getByTestId('mode'), { target: { value: 'h-r' } });
  if (action === 'import') await act(async () => fireEvent.change(screen.getByTestId('import'), { target: { files: [{ size: 10, text: async () => '{}' }] } }));
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(fake.reset).not.toHaveBeenCalled(); expect(fake.imported).not.toHaveBeenCalled();
  expect((screen.getByTestId('mode') as HTMLSelectElement).value).toBe('r-r');
  expect(screen.getByTestId('last-move').textContent).toContain('5七V→5六VI');
});

it('gives each square a readable location, side and selection state', () => {
  fake.snap.board[382] = 1; // 5七V, Black pawn (hand-calculated index)
  render(<App />);
  expect(screen.getByRole('button', { name: '5七V 先手 歩' }).getAttribute('aria-pressed')).toBe('false');
  expect(screen.getByRole('button', { name: '5六V 空きマス' })).toBeTruthy();
});
