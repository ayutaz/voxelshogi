// Handwritten metadata only: these hashes/sizes are not real published models.
// Parameter counts are pinned by docs/P6_OPERATOR_RESULTS.md, not the parser.
export const researchCounts = { full: 25_783_688, axial: 25_783_688, geometry: 26_098_120, cnn: 28_606_344 };
export type ArchitectureFixture = keyof typeof researchCounts;
export const researchNames = ['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b'];
const file = (path: string, bytes: number, sha256 = 'a'.repeat(64)) => ({ path, bytes, sha256 });
export function researchIdentity(architecture: ArchitectureFixture = 'full') {
  return { id: `voxelshogi-research-${architecture}-67003`, license: 'Apache-2.0', sourceCommit: 'c'.repeat(40),
    profile: 'research-m-v1' as const, architecture };
}
export function researchFixture(architecture: ArchitectureFixture = 'full') {
  const identity = researchIdentity(architecture);
  return {
    schema: 1, id: identity.id, trained: true, license: 'Apache-2.0', sourceCommit: identity.sourceCommit, sourceDirty: false,
    numericContract: 'voxelshogi-trained-numeric-v1', inputSchema: 'voxelshogi-standard-features-v1', ruleset: 'voxelshogi-standard-v1',
    seed: 67003, parameters: researchCounts[architecture],
    inputs: { features: { dtype: 'float32', shape: [1, 729, 43] } },
    outputs: { policy: { dtype: 'float32', shape: [1, 1_067_985] }, value: { dtype: 'float32', shape: [1, 1] } },
    checkpoint: file('model.safetensors', 114_500_000, 'd'.repeat(64)),
    research: {
      schema: 'voxelshogi-research-inference-v1',
      architecture: { architecture, side: 9, width: architecture === 'cnn' ? 256 : 512, layers: 8, heads: 8, ffn: 2048, policy_rank: 64 },
      trainingSourceCommit: 'e'.repeat(40), trainingBindingSha256: 'f'.repeat(64), selectedUpdate: 256, totalUpdates: 1024,
      selection: file('selection.json', 1200), evaluationProtocolSha256: '1'.repeat(64), finalRootsSha256: '2'.repeat(64),
    },
    fixtures: researchNames.map((name, i) => ({ name, side: i === 1 ? 'w' : 'b', record: { ruleset_id: 'voxelshogi-standard-v1' }, input: file(`inputs/${name}.f32`, 125_388) })),
    variants: (['fp32', 'fp16', 'int8'] as const).map((precision, i) => ({
      id: precision, precision, model: file(`${precision}.onnx`, [138_880_000, 75_000_000, 40_000_000][i]!, String(i + 3).repeat(64)),
      ...(i === 0 ? {} : { conversion: { method: i === 1 ? 'fp16-weight-only' : 'symmetric-per-tensor-weight-only-int8', compute: 'float32', activations: 'float32',
        ...(i === 1 ? { convertedTensors: 16, convertedElements: 1_000_000 } : { quantizedTensors: 16, quantizedElements: 1_000_000 }) } }),
      references: Object.fromEntries(researchNames.map(name => [name, { policy: file(`reference/${precision}/${name}-policy.f32`, 4_271_940), value: file(`reference/${precision}/${name}-value.f32`, 4) }])),
      ...(i === 0 ? {} : { fp32Difference: Object.fromEntries(researchNames.map(name => [name, {
        policy: { elements: 1_067_985, maxAbs: 0.01, mae: 0.001, rmse: 0.002, maxRelative: 0.1, argmaxEqual: false },
        value: { elements: 1, maxAbs: 0.01, mae: 0.01, rmse: 0.01, maxRelative: 0.1, argmaxEqual: true },
      }])) }),
      evaluation: { scope: 'final-holdout-v1', complete: true, gameCount: 24, modelSha256: String(i + 3).repeat(64), weightsSha256: 'd'.repeat(64), report: file(`evaluation/${precision}.json`, 1300) },
    })),
  };
}
