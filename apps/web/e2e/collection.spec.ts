import { expect, test } from '@playwright/test';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';
import { loadWasm } from '../tests/loadWasm';

loadWasm();
test('consent is OFF by default and a completed game is not sent retroactively', async ({ page }) => {
  let posts = 0;
  await page.route('**/api/collection', route => route.fulfill({ json: { enabled: true, consent: 'game-research-v1' } }));
  await page.route('**/api/games', route => { posts++; return route.fulfill({ status: 500 }); });
  await page.goto('/');
  await page.getByTestId('mode').selectOption('h-r');
  await expect(page.getByTestId('collection-consent')).toBeEnabled();
  await expect(page.getByTestId('collection-consent')).not.toBeChecked();
  await page.getByRole('button', { name: '投了', exact: true }).click();
  await expect(page.getByTestId('status')).toContainText('後手の勝ち');
  await page.getByTestId('collection-consent').check();
  await expect(page.getByTestId('ai-phase')).toHaveText('対局終了');
  expect(posts).toBe(0);
});

test('a consented finished game is sent once, with real engine outcome and no model bytes', async ({ page }) => {
  const posts: Record<string, unknown>[] = [];
  await page.route('**/api/collection', route => route.fulfill({ json: { enabled: true, consent: 'game-research-v1' } }));
  await page.route('**/api/games', route => {
    const body = route.request().postDataJSON() as Record<string, unknown>; posts.push(body);
    return route.fulfill({ status: 201, json: { requestId: body.requestId, status: 'received_unverified' } });
  });
  await page.goto('/'); await page.getByTestId('mode').selectOption('h-r');
  await page.getByTestId('collection-consent').check();
  await page.getByRole('button', { name: '投了', exact: true }).click();
  await expect(page.getByTestId('collection-receipt')).toBeVisible();
  expect(posts).toHaveLength(1);
  expect(posts[0]).toMatchObject({ consent: 'game-research-v1', ending: 'finished', mode: 'h-r',
    record: { moves: [], result: { Win: { winner: 'White', reason: 'Resignation' } }, termination: 'Resignation' } });
  const replay = Game.fromRecordJson(JSON.stringify(posts[0]!.record));
  try { expect(replay.isFinished()).toBe(true); } finally { replay.free(); }
  expect(Object.keys(posts[0]!).sort()).toEqual(['applicationCommit', 'conditionsScope', 'consent', 'ending', 'mode', 'record', 'requestId', 'schema', 'selectedAgents']);
});

test('a failed interruption upload preserves play and a manual retry uses the same body', async ({ page }) => {
  const bodies: string[] = [];
  await page.route('**/api/collection', route => route.fulfill({ json: { enabled: true, consent: 'game-research-v1' } }));
  await page.route('**/api/games', route => {
    const body = route.request().postData()!; bodies.push(body);
    return bodies.length === 1 ? route.fulfill({ status: 503, json: { error: 'collection_unavailable' } })
      : route.fulfill({ status: 200, json: { requestId: JSON.parse(body).requestId, status: 'received_unverified' } });
  });
  await page.goto('/');
  await page.getByTestId('difficulty-b').selectOption('easy'); await page.getByTestId('difficulty-w').selectOption('easy');
  await page.getByTestId('collection-consent').check();
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await page.getByTestId('collection-abort').click();
  await expect(page.getByRole('alert')).toContainText('送信できませんでした');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await page.getByRole('button', { name: '同じ棋譜を再送' }).click();
  await expect(page.getByTestId('collection-receipt')).toBeVisible();
  expect(bodies).toHaveLength(2); expect(bodies[0]).toBe(bodies[1]);
  const record = JSON.parse(bodies[0]!).record;
  expect(record.moves).toHaveLength(1); expect(record.termination).toBe('Abandoned');
  const replay = Game.fromRecordJson(JSON.stringify(record));
  try { expect(replay.moveCount()).toBe(1); expect(replay.isFinished()).toBe(true); } finally { replay.free(); }
});
