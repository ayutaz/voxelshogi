// Run after building WASM. Compare complete native/browser-target results, not
// just scores; shared fixtures also have independent hand-counted assertions.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Game, initSync } from '../../apps/web/src/wasm/pkg/voxelshogi_wasm.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
const fixtures = JSON.parse(readFileSync(new URL('../../crates/voxelshogi-wasm/tests/fixtures/search.json', import.meta.url), 'utf8'));
const native = JSON.parse(execFileSync('cargo', ['run', '--quiet', '--locked', '-p', 'voxelshogi-wasm', '--example', 'search_fixtures'], { cwd: root, encoding: 'utf8' }));
initSync({ module: readFileSync(new URL('../../apps/web/src/wasm/pkg/voxelshogi_wasm_bg.wasm', import.meta.url)) });
assert.equal(fixtures.length, 12);
assert.equal(native.length, fixtures.length);
for (const [i, f] of fixtures.entries()) {
  const g = Game.fromRecordJson(JSON.stringify(f.record));
  try {
    assert.deepEqual(JSON.parse(g.bestMove(JSON.stringify(f.config))), native[i], f.name);
    console.log(`Native/WASM parity: ${f.name}`);
  } finally { g.free(); }
}
