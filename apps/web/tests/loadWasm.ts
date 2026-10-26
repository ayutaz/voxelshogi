// Loads the real WASM engine in Node for tests (no mocks).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { initSync } from '../src/wasm/pkg/voxelshogi_wasm.js';

let loaded = false;
export function loadWasm(): void {
  if (loaded) return;
  // Avoid Vite's browser-asset rewrite when this helper runs under jsdom.
  const path = resolve(dirname(fileURLToPath(import.meta.url)), '../src/wasm/pkg/voxelshogi_wasm_bg.wasm');
  initSync({ module: readFileSync(path) });
  loaded = true;
}
