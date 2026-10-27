// Input snapshots, not test oracles: Rust supplies the board/hands/record.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { Game, initSync } from '../apps/web/src/wasm/pkg/voxelshogi_wasm.js';

initSync({ module: readFileSync(new URL('../apps/web/src/wasm/pkg/voxelshogi_wasm_bg.wasm', import.meta.url)) });
const fixtures = JSON.parse(readFileSync(new URL('../crates/voxelshogi-wasm/tests/fixtures/search.json', import.meta.url), 'utf8'));
const samples = [];
function capture(name, game) {
  try { samples.push({ name, record: JSON.parse(game.recordJson()), board: [...game.board()], hands: [...game.hands()], side: game.sideToMove() }); }
  finally { game.free(); }
}
capture('initial-b', new Game());
const white = new Game(); white.play('577567');
capture('after-one-w', white);
for (const name of ['mate-in-one-b', 'material-b']) capture(name, Game.fromRecordJson(JSON.stringify(fixtures.find((f) => f.name === name).record)));
assert.equal(samples.length, 4);
const path = new URL('../export/fixtures/positions.json', import.meta.url);
if (process.argv.includes('--check')) assert.deepEqual(JSON.parse(readFileSync(path, 'utf8')), samples);
else writeFileSync(path, JSON.stringify(samples) + '\n');
console.log(`${samples.length} fixed model inputs ${process.argv.includes('--check') ? 'verified' : 'written'}`);
