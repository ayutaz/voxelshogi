import { expect, test } from './test';
import { selectSetting, settingsAction, sliceAt } from './arena-controls';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';
import { loadWasm } from '../tests/loadWasm';

loadWasm();
test('automatically saves a human move and terminal result without any collection controls', async ({ page }) => {
  const posts: Record<string, unknown>[] = [];
  await page.route('**/api/games', route => {
    const p = route.request().postDataJSON(); posts.push(p);
    return route.fulfill({ json: { gameId: p.gameId, requestId: p.requestId, version: p.version, status: 'received_unverified' } });
  });
  await page.goto('/');
  await expect(page.getByTestId('collection-consent')).toHaveCount(0);
  await selectSetting(page, 'difficulty-w', 'easy'); await selectSetting(page, 'mode', 'h-r');
  await page.locator('.board2d [data-square="382"]').click(); await page.locator('.board2d [data-square="373"]').click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await settingsAction(page, '投了');
  await expect.poll(() => posts.filter(p => p.state === 'finished').length).toBe(1);
  expect(new Set(posts.map(p => p.gameId)).size).toBe(1);
  const final = posts.at(-1)!;
  expect(final).toMatchObject({ schema: 2, policy: 'automatic-game-v2', mode: 'h-r', conditionsScope: 'game-start',
    record: { moves: ['577567', expect.any(String)], result: { Win: { winner: 'White', reason: 'Resignation' } }, termination: 'Resignation' } });
  expect(Object.keys(final).sort()).toEqual(['applicationCommit','conditionsScope','gameId','mode','policy','record','requestId','schema','selectedAgents','state','version']);
  const replay = Game.fromRecordJson(JSON.stringify(final.record));
  try { expect(replay.moveCount()).toBe(2); expect(replay.isFinished()).toBe(true); } finally { replay.free(); }
  await page.getByRole('button', { name: '最初から振り返る', exact: true }).click();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番'); await page.getByTestId('redo').click();
  expect(posts.filter(p => p.state === 'finished')).toHaveLength(1);
});

test('automatic retries preserve their body and failures never block further legal play', async ({ page }) => {
  const bodies: string[] = [];
  await page.route('**/api/games', route => {
    const body = route.request().postData()!; bodies.push(body); const p = JSON.parse(body);
    return bodies.length === 1 ? route.fulfill({ status: 503, json: { error: 'unavailable' } })
      : route.fulfill({ json: { gameId: p.gameId, requestId: p.requestId, version: p.version, status: 'received_unverified' } });
  });
  await page.goto('/'); await selectSetting(page,'difficulty-b','easy'); await selectSetting(page,'difficulty-w','easy');
  await page.getByTestId('ai-step').click(); await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await page.getByTestId('ai-step').click(); await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await expect.poll(() => bodies.length, { timeout: 10000 }).toBeGreaterThanOrEqual(2);
  expect(bodies[0]).toBe(bodies[1]); await expect(page.getByText(/送信できません|送信中|データ送信/)).toHaveCount(0);
  const p = JSON.parse(bodies[0]!); expect(p.record.moves).toHaveLength(1);
  const replay = Game.fromRecordJson(JSON.stringify(p.record));
  try { expect(replay.moveCount()).toBe(1); } finally { replay.free(); }
});

test('imported records and explicit branches from imports produce no collection requests', async ({ page }) => {
  let posts = 0;
  await page.route('**/api/games', route => { posts++; return route.fulfill({ status: 503 }); });
  await page.goto('/'); await selectSetting(page,'mode','h-r');
  const engine = new Game(); let record: string;
  try { engine.play('577567'); record = engine.recordJson(); } finally { engine.free(); }
  await page.getByTestId('import').setInputFiles({ name: 'import.json', mimeType: 'application/json', buffer: Buffer.from(record) });
  await expect(page.getByRole('alert')).toContainText('棋譜を読み込みました');
  await page.getByTestId('undo').click(); await page.getByRole('button', { name: 'この局面から対戦を分岐', exact: true }).click();
  await sliceAt(page,'4');
  await page.locator('.board2d [data-square="382"]').click(); await page.locator('.board2d [data-square="373"]').click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番'); expect(posts).toBe(0);
});
