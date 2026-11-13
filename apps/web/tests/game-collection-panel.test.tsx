// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { GameCollectionPanel } from '../src/collection/GameCollectionPanel';
import type { GameSubmission } from '../src/collection/contract';

const posts: string[] = [];
const agents: GameSubmission['selectedAgents'] = { b: { kind: 'easy', seed: 42 }, w: { kind: 'easy', seed: 42 } };
const record = { ruleset_id: 'voxelshogi-standard-v1', initial: '8k/9/9/9/9/9/9/9/K8 b - 1', moves: ['191281'], result: null, termination: null };
const props = () => ({ mode: 'r-r' as const, selectedAgents: agents, getRecord: () => JSON.stringify(record), finished: false, canAbort: true, imported: false, onAbort: vi.fn() });
beforeEach(() => {
  posts.length = 0;
  vi.stubGlobal('fetch', vi.fn(async (path: string, options?: RequestInit) => {
    if (path === '/api/collection') return Response.json({ enabled: true, consent: 'game-research-v1' });
    if (path === '/build-info.json') return Response.json({ commit: 'a'.repeat(40) });
    if (path === '/api/games') { const body = String(options?.body); posts.push(body); return Response.json({ requestId: JSON.parse(body).requestId, status: 'received_unverified' }, { status: 201 }); }
    throw new Error('unexpected URL');
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
async function ready() { await waitFor(() => expect((screen.getByTestId('collection-consent') as HTMLInputElement).disabled).toBe(false)); }

it('defaults OFF and never posts a finished game without consent', async () => {
  const original = props(), mounted = render(<GameCollectionPanel {...original} />); await ready();
  expect((screen.getByTestId('collection-consent') as HTMLInputElement).checked).toBe(false);
  mounted.rerender(<GameCollectionPanel {...original} finished />);
  await act(async () => {}); expect(posts).toEqual([]);
  fireEvent.click(screen.getByTestId('collection-consent')); // enabling after the end is not retroactive
  await act(async () => {}); expect(posts).toEqual([]);
});
it('sends an opted-in finished game once and displays its receipt', async () => {
  const original = props(), mounted = render(<GameCollectionPanel {...original} />); await ready();
  fireEvent.click(screen.getByTestId('collection-consent'));
  const final = { ...record, result: { Win: { winner: 'Black', reason: 'Resignation' } }, termination: 'Resignation' };
  mounted.rerender(<GameCollectionPanel {...original} finished getRecord={() => JSON.stringify(final)} />);
  await screen.findByText(/保存されました/);
  expect(posts).toHaveLength(1);
  expect(JSON.parse(posts[0]!)).toMatchObject({ consent: 'game-research-v1', ending: 'finished', record: final, applicationCommit: 'a'.repeat(40) });
  mounted.rerender(<GameCollectionPanel {...original} finished getRecord={() => JSON.stringify(final)} />);
  await act(async () => {}); expect(posts).toHaveLength(1);
  expect(screen.getByTestId('collection-receipt').textContent).toContain(JSON.parse(posts[0]!).requestId);
});
it('saves only an explicitly requested interruption and keeps all moves', async () => {
  const original = props(); render(<GameCollectionPanel {...original} />); await ready();
  fireEvent.click(screen.getByTestId('collection-consent'));
  fireEvent.click(screen.getByTestId('collection-abort'));
  await screen.findByText(/保存されました/);
  expect(original.onAbort).toHaveBeenCalledTimes(1);
  expect(JSON.parse(posts[0]!)).toMatchObject({ ending: 'aborted', record: { moves: ['191281'], termination: 'Abandoned', result: null } });
  expect((screen.getByTestId('collection-abort') as HTMLButtonElement).disabled).toBe(true);
});
it('leaves imported records unsent even when the feature is available', async () => {
  render(<GameCollectionPanel {...props()} imported />);
  await waitFor(() => expect(screen.getByText(/読み込んだ棋譜は送信しません/)).toBeTruthy());
  expect((screen.getByTestId('collection-consent') as HTMLInputElement).disabled).toBe(true);
  expect(posts).toEqual([]);
});
it('retries a frozen failed submission without changing the record or selected AI', async () => {
  const original = props(), mounted = render(<GameCollectionPanel {...original} />); await ready();
  const fetcher = vi.mocked(fetch);
  fetcher.mockRejectedValueOnce(new Error('offline'));
  fireEvent.click(screen.getByTestId('collection-consent'));
  fireEvent.click(screen.getByTestId('collection-abort'));
  await screen.findByText(/送信できませんでした/);
  const failedBody = String(fetcher.mock.calls.find(call => call[0] === '/api/games')![1]!.body);
  mounted.rerender(<GameCollectionPanel {...original} getRecord={() => 'changed record'} selectedAgents={{ b: { kind: 'easy', seed: 99 }, w: agents.w }} />);
  fireEvent.click(screen.getByRole('button', { name: '同じ棋譜を再送' }));
  await screen.findByText(/保存されました/);
  expect(posts).toEqual([failedBody]);
});
