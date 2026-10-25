// Loads the real WASM engine in Node for tests (no mocks).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { initSync } from '../src/wasm/pkg/voxelshogi_wasm.js';

let loaded = false;
export function loadWasm(): void {
  if (loaded) return;
  const url = new URL('../src/wasm/pkg/voxelshogi_wasm_bg.wasm', import.meta.url);
  initSync({ module: readFileSync(fileURLToPath(url)) });
  loaded = true;
}
