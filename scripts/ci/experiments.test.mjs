import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarize, representative } from '../experiment-pack.mjs';

test('summary uses all outcomes including draws and hand-counted event intervals', () => {
  const games = [
    {
      record: {
        seed: 1,
        swapped: false,
        moves: ['a', 'b', 'c', 'd'],
        outcome: { winner: 'Black', reason: 'target' },
        nodes: 10,
      },
      captured: [5, 2],
      events: [1, 4],
      cross: 2,
    },
    {
      record: { seed: 1, swapped: true, moves: ['a', 'b'], outcome: { winner: null, reason: 'move_limit' }, nodes: 6 },
      captured: [0, 0],
      events: [],
      cross: 0,
    },
  ];
  const s = summarize(games);
  assert.equal(s.games, 2);
  assert.equal(s.plies.median, 2);
  assert.equal(s.plies.p90, 4);
  assert.deepEqual(s.wins, { Black: 1, White: 0, draw: 1 });
  assert.deepEqual(s.reasons, { target: 1, move_limit: 1 });
  assert.equal(s.meanCapturedKings, 3.5);
  assert.equal(s.crossLayerRate, 2 / 6);
  assert.equal(s.firstKingCapture.median, 1);
  assert.equal(s.gamesWithoutKingCapture, 1);
  assert.equal(s.longestKingDrought.p90, 2);
  assert.equal(s.nodes, 16);
});
test('representative is nearest median length including unfinished games, with deterministic ties', () => {
  const game = (seed, length) => ({ record: { seed, swapped: false, moves: Array(length) } });
  const a = game(3, 400),
    b = game(1, 10),
    c = game(2, 400);
  assert.equal(representative([a, b, c]), c);
  assert.throws(() => summarize([]));
  assert.throws(() => representative([]));
});

test('uncertainty resamples complete seed pairs rather than individual games', async () => {
  const { pairInterval } = await import('../experiment-pack.mjs');
  const games = [false, true].map((swapped) => ({ record: { seed: 7, swapped, outcome: { winner: 'Black' } } }));
  assert.deepEqual(
    pairInterval(games, () => 1),
    [1, 1],
  );
  assert.deepEqual(
    pairInterval(games, (g) => Number(g.record.swapped)),
    [0.5, 0.5],
  );
  assert.throws(() => pairInterval(games.slice(0, 1), () => 1));
});
