import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const read = (file) => readFileSync(new URL(`../../${file}`, import.meta.url), 'utf8');
const node = read('.node-version').trim();
const pnpm = JSON.parse(read('apps/web/package.json')).packageManager.split('@')[1];
const wasm = read('crates/voxelshogi-wasm/Cargo.toml').match(/^wasm-bindgen\s*=\s*"=([^"]+)"/m)?.[1];
assert.ok(wasm, 'Cargo manifest must pin wasm-bindgen exactly');
assert.equal(process.versions.node, node, 'Node must match .node-version');
assert.equal(execFileSync('pnpm', ['--version'], { encoding: 'utf8' }).trim(), pnpm, 'pnpm must match packageManager');
assert.equal(execFileSync('wasm-bindgen', ['--version'], { encoding: 'utf8' }).trim(), `wasm-bindgen ${wasm}`, 'wasm-bindgen CLI must match Cargo');
console.log(`Versions match: Node ${node}, pnpm ${pnpm}, wasm-bindgen ${wasm}`);
