const ref = (path: string, bytes = 3) => ({ path, bytes, sha256: 'a'.repeat(64) });
export const modelFixture = () => ({ schema: 1, id: 'test-untrained', trained: false, license: 'Apache-2.0',
  inputSchema: 'voxelshogi-standard-features-v1', ruleset: 'voxelshogi-standard-v1', seed: 314159, parameters: 5_021_064,
  inputs: { features: { shape: [1, 729, 43], dtype: 'float32' } },
  outputs: { policy: { shape: [1, 1_067_985], dtype: 'float32' }, value: { shape: [1, 1], dtype: 'float32' } },
  fixtures: [{ name: 'initial-b', side: 'b', input: ref('inputs/initial.f32', 125388), record: { ruleset_id: 'voxelshogi-standard-v1' } }],
  variants: [{ id: 'fp32', precision: 'fp32', model: ref('fp32.onnx'), references: { 'initial-b': { policy: ref('reference/policy.f32', 4_271_940), value: ref('reference/value.f32', 4) } } }],
});
export const deploymentFixture = () => ({ schema: 1, publication: true, model: ref('models/hash/manifest.json'),
  modelNotices: [ref('models/hash/LICENSE.txt'), ref('models/hash/MODEL_CARD.md')],
  runtime: { version: '1.31.1', bundle: ref('runtime/bundle.mjs'), bootstrap: ref('runtime/bootstrap.mjs'),
    wasm: { path: 'runtime.wasm', bytes: 6, sha256: 'b'.repeat(64), parts: [ref('runtime/part0.bin'), ref('runtime/part1.bin')] },
    notices: [ref('runtime/LICENSE'), ref('runtime/ThirdPartyNotices.txt')] },
});
