// Linux CI only: actual Rust replay. Mac runs only the pure policy tests.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { beforeAll, expect, it } from 'vitest';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';
import { encodePosition, selectPolicyMove } from '../src/inference/policy-contract';
import { POLICY_ELEMENTS } from '../src/inference/manifest';
import { loadWasm } from './loadWasm';

// Python-produced input bytes from the verified M3 final manifest:
// 412f9e6877f7138be9e205d42e8f27558b0766a1408d84c803bb3640c7598f80
// docs/experiments/m3-completion-publication.json pins that exact manifest.
// These are input oracles, independent of the new TypeScript encoder/model weights.
const hashes: Record<string, string> = {
  'initial-b': 'e45e6524437c01d7ad4d61db1faded24a2b1d0aaaf814fbbbcb42aa198f0642a',
  'after-one-w': 'fea43477b26cf5b66d8da7c9123309a2bb4a20821952e0ab47c845347135d1b6',
  'mate-in-one-b': 'c817286c328d398fe4026bc5ac9c888c6aab963fd19314d527e473e82d80c3b6',
  'material-b': '9f98fdc7ba475e87e9128faeded6254a3b809ab0c96d1d7e50d80be5b8dfc5ca',
};
const fixtures = JSON.parse(readFileSync(new URL('../../../export/fixtures/positions.json', import.meta.url), 'utf8')) as { name: string; record: object; side: 'b' | 'w' }[];
beforeAll(loadWasm);
for (const fixture of fixtures) {
  it(`matches the independently frozen Python input after Rust replay: ${fixture.name}`, () => {
    const game = Game.fromRecordJson(JSON.stringify(fixture.record));
    try {
      expect(game.sideToMove()).toBe(fixture.side);
      const before = game.recordJson(), features = encodePosition(game.board(), game.hands(), fixture.side);
      expect(createHash('sha256').update(new Uint8Array(features.buffer)).digest('hex')).toBe(hashes[fixture.name]);
      const legal = game.legalMoves(), policy = new Float32Array(POLICY_ELEMENTS); policy[0] = 1000;
      const result = selectPolicyMove(policy, new Float32Array([0]), legal, fixture.side);
      expect(legal).toContain(result.move); expect(result.action).not.toBe(0);
      expect(result.rawLegal).toBe(false); expect(game.recordJson()).toBe(before);
    } finally { game.free(); }
  });
}
