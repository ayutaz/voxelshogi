// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { flushSync } from 'react-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import type { AiStatus } from '../src/ai/arena-controller';
import type { Snapshot } from '../src/game/store';

const fake = vi.hoisted(() => ({ snap: {} as Snapshot, record: '', listeners: new Set<() => void>(), reset: vi.fn(), imported: vi.fn(), configure: vi.fn(), goto: vi.fn(), step: vi.fn(), paused: vi.fn(), status: {} as AiStatus, aiListeners: new Set<() => void>() }));
vi.mock('../src/game/store', () => ({ MAX_IMPORT_BYTES: 4e6, GameStore: class {
  subscribe = (fn: () => void) => { fake.listeners.add(fn); return () => fake.listeners.delete(fn); };
  snapshot = () => fake.snap;
  newGame = fake.reset; goto = fake.goto;
  importRecord = fake.imported;
  exportRecord = () => fake.record;
} }));
vi.mock('../src/ai/arena-controller', () => ({ DEFAULT_AI_OPTIONS: { seed: 42, limits: { maxDepth: 6, maxNodes: 50000, maxTimeMs: 1000 } }, ArenaController: class {
  subscribe = (fn: () => void) => { fake.aiListeners.add(fn); return () => { fake.aiListeners.delete(fn); }; }; snapshot = () => fake.status; step = fake.step;
  configure = fake.configure; pause = fake.paused; resume = () => {}; suspend = () => {}; dispose = () => {};
  journal = { clear: () => {} };
} }));
vi.mock('../src/renderer/Board3D', () => ({ Board3D: () => <div data-testid="fake-3d" /> }));
beforeEach(() => {
  fake.status = { phase: 'paused', error: null, last: null };
  fake.snap = { revision: 0, side: 'b', ply: 0, moveCount: 0, moves: [], finished: false, result: null,
    lastMove: null, legal: [], board: new Uint8Array(729), hands: new Uint8Array(14),
    inCheck: { b: false, w: false }, kingSquare: { b: 0, w: 728 }, hash: '0000000000000000' };
  fake.imported.mockReturnValue({ ok: true });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals(); });
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

it('does not send an imported terminal game even if the external store flushes before React state', async () => {
  const posts: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/collection') return Response.json({ enabled: true, consent: 'game-research-v1' });
    if (url === '/build-info.json') return Response.json({ commit: 'a'.repeat(40) });
    const body = JSON.parse(String(options?.body)); posts.push(body);
    return Response.json({ requestId: body.requestId, status: 'received_unverified' }, { status: 201 });
  }));
  render(<App />);
  await screen.findByTestId('collection-consent');
  await act(async () => {});
  expect((screen.getByTestId('collection-consent') as HTMLInputElement).disabled).toBe(false);
  fireEvent.click(screen.getByTestId('collection-consent'));
  fake.imported.mockImplementation(() => {
    fake.record = JSON.stringify({ ruleset_id: 'voxelshogi-standard-v1', initial: '8k/9/K8 b - 1', moves: [], result: { Win: { winner: 'White', reason: 'Resignation' } }, termination: 'Resignation' });
    flushSync(() => {
      fake.snap = { ...fake.snap, finished: true, result: { kind: 'win', winner: 'w', reason: 'Resignation' } };
      for (const fn of fake.listeners) fn();
    });
    return { ok: true };
  });
  await act(async () => fireEvent.change(screen.getByTestId('import'), { target: { files: [{ size: 10, text: async () => '{}' }] } }));
  expect(fake.imported).toHaveBeenCalledTimes(1);
  expect(posts).toEqual([]);
});


it('keeps the one-move control focused while busy and ignores repeated activation', () => {
  render(<App />); const step = screen.getByTestId('ai-step') as HTMLButtonElement; step.focus();
  act(() => { fake.status = { ...fake.status, phase: 'thinking' }; for (const fn of fake.aiListeners) fn(); });
  expect(step.disabled).toBe(false); expect(step.getAttribute('aria-disabled')).toBe('true');
  expect(document.activeElement).toBe(step); fireEvent.click(step); expect(fake.step).not.toHaveBeenCalled();
  act(() => { fake.status = { ...fake.status, phase: 'paused' }; for (const fn of fake.aiListeners) fn(); });
  fireEvent.click(step); expect(fake.step).toHaveBeenCalledTimes(1);
});
it('returns to the retained latest position before restarting from history', () => {
  fake.snap = { ...fake.snap, ply: 1, moveCount: 2, moves: ['575566','535544'] };
  render(<App />); fireEvent.click(screen.getByRole('button', { name: '最新局面から再開' }));
  expect(fake.goto).toHaveBeenCalledWith(2);
  expect(fake.configure.mock.calls.at(-1)![0]).toMatchObject({ running: true });
});
it('places the current move before the board so layer changes have a visible explanation', () => {
  const { container } = render(<App />);
  const board = container.querySelector('.board2d')!;
  expect(screen.getByTestId('last-move').compareDocumentPosition(board) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});


it('keeps the interrupt control in the same row without hiding it between AI phases', () => {
  render(<App />); const interrupt = screen.getByTestId('cancel-search') as HTMLButtonElement;
  const row = screen.getByTestId('ai-step').parentElement;
  expect(interrupt.parentElement).toBe(row); expect(interrupt.hidden).toBe(false);
  expect(interrupt.getAttribute('aria-disabled')).toBe('true');
  fireEvent.click(interrupt); expect(fake.paused).not.toHaveBeenCalled();
  act(() => { fake.status = { ...fake.status, phase: 'thinking' }; for (const fn of fake.aiListeners) fn(); });
  expect(screen.getByTestId('cancel-search')).toBe(interrupt);
  expect(interrupt.parentElement).toBe(row); expect(interrupt.hidden).toBe(false);
  expect(interrupt.getAttribute('aria-disabled')).toBe('false'); fireEvent.click(interrupt);
  expect(fake.paused).toHaveBeenCalledTimes(1);
  act(() => { fake.status = { ...fake.status, phase: 'paused' }; for (const fn of fake.aiListeners) fn(); });
  expect(screen.getByTestId('cancel-search')).toBe(interrupt);
  expect(interrupt.hidden).toBe(false); expect(interrupt.getAttribute('aria-disabled')).toBe('true');
});
