import { expect, it } from 'vitest';
import { parseModel, parseTrainedModel } from '../src/inference/manifest';
import { parseResearchModel } from '../src/inference/research-manifest';
import { researchCounts, researchFixture, researchIdentity, type ArchitectureFixture } from './research-model-fixtures';
import { releaseFixture, trainedFixture } from './local-model-fixtures';

for (const architecture of Object.keys(researchCounts) as ArchitectureFixture[]) {
  it(`accepts the reviewed ${architecture} M profile and all three evaluated formats`, () => {
    const model = researchFixture(architecture), parsed = parseResearchModel(model, researchIdentity(architecture));
    expect(parsed.parameters).toBe(researchCounts[architecture]);
    expect(parsed.variants.map(v => v.precision)).toEqual(['fp32', 'fp16', 'int8']);
    expect(parsed.variants[0]!.model.bytes).toBe(138_880_000);
    expect(parsed.research.trainingSourceCommit).toBe('e'.repeat(40));
    // Quantization may reduce accuracy: metadata must retain a valid negative result.
    expect(parsed.variants[2]!.fp32Difference!['initial-b']!.policy.argmaxEqual).toBe(false);
  });
}

function set(value: unknown, path: string, replacement: unknown) {
  const parts = path.split('.'); let object = value as Record<string, unknown>;
  for (const part of parts.slice(0, -1)) object = object[part] as Record<string, unknown>;
  object[parts.at(-1)!] = replacement;
}
const invalid: [string, unknown][] = [
  ['schema', 2], ['trained', false], ['id', 'another-model'], ['sourceDirty', true], ['sourceCommit', 'b'.repeat(40)], ['license', 'MIT'],
  ['numericContract', 'unknown'], ['inputSchema', 'other'], ['ruleset', 'other'], ['seed', -1], ['seed', 1.5], ['seed', NaN], ['parameters', 5_021_064],
  ['inputs.features.shape', [1, 729, 42]], ['outputs.policy.shape', [1, 1_067_984]], ['outputs.value.dtype', 'float16'],
  ['checkpoint.path', '../model.safetensors'], ['checkpoint.sha256', 'bad'], ['checkpoint.bytes', 512 * 1024 * 1024 + 1],
  ['research.schema', 'unknown'], ['research.architecture.architecture', 'axial'], ['research.architecture.side', 8], ['research.architecture.width', 256],
  ['research.architecture.layers', 7], ['research.architecture.heads', 4], ['research.architecture.ffn', 1024], ['research.architecture.policy_rank', 32],
  ['research.trainingSourceCommit', 'main'], ['research.trainingBindingSha256', 'bad'], ['research.selectedUpdate', 0], ['research.selectedUpdate', 1025],
  ['research.totalUpdates', 1.5], ['research.totalUpdates', 1_000_001], ['research.selection.path', 'model.safetensors'], ['research.selection.bytes', 1_048_577],
  ['research.evaluationProtocolSha256', 'bad'], ['research.finalRootsSha256', 'bad'],
  ['fixtures', []], ['fixtures.1.name', 'initial-b'], ['fixtures.1.side', 'b'], ['fixtures.0.input.bytes', 125_387], ['fixtures.0.record.ruleset_id', 'other'],
  ['variants', []], ['variants.1.precision', 'fp32'], ['variants.0.model.path', 'other.onnx'], ['variants.0.model.bytes', 512 * 1024 * 1024 + 1],
  ['variants.1.conversion.compute', 'float16'], ['variants.1.conversion.method', 'onnxconverter-common-float16'], ['variants.2.conversion.compute', 'int8'],
  ['variants.2.conversion.activations', 'int8'], ['variants.2.conversion.quantizedTensors', 0], ['variants.2.conversion.quantizedElements', 25_783_689],
  ['variants.1.references.initial-b.policy.bytes', 4_271_936], ['variants.2.references.material-b.value.bytes', 8],
  ['variants.1.fp32Difference.initial-b.policy.elements', 1], ['variants.1.fp32Difference.initial-b.policy.argmaxEqual', 'yes'], ['variants.1.fp32Difference.initial-b.value.maxAbs', Infinity],
  ['variants.2.evaluation.scope', 'development-v1'], ['variants.2.evaluation.complete', false], ['variants.2.evaluation.gameCount', 23],
  ['variants.2.evaluation.modelSha256', 'a'.repeat(64)], ['variants.2.evaluation.weightsSha256', 'a'.repeat(64)], ['variants.2.evaluation.report.path', 'evaluation/fp32.json'],
];
for (const [path, value] of invalid) it(`rejects inconsistent M release metadata: ${path}=${String(value)}`, () => {
  const model = researchFixture(); set(model, path, value);
  expect(() => parseResearchModel(model, researchIdentity())).toThrow();
});

it('requires an explicit approved M identity and never relaxes the existing S or untrained parser', () => {
  expect(() => parseResearchModel(researchFixture(), { ...researchIdentity(), profile: 'unknown' } as never)).toThrow();
  expect(() => parseResearchModel(researchFixture(), { ...researchIdentity(), architecture: 'unknown' } as never)).toThrow();
  expect(() => parseModel(researchFixture())).toThrow();
  expect(() => parseTrainedModel(researchFixture(), releaseFixture())).toThrow();
  const legacy = trainedFixture(); legacy.variants[0]!.model.bytes = 138_880_000;
  expect(() => parseTrainedModel(legacy, releaseFixture())).toThrow();
  expect(parseTrainedModel(trainedFixture(), releaseFixture()).parameters).toBe(5_021_064);
});

it('requires every reference, every format difference and distinct artifact paths', () => {
  for (const path of ['variants.0.references.initial-b', 'variants.2.fp32Difference.material-b', 'variants.1.conversion', 'research.selection']) {
    const model = researchFixture(); set(model, path, undefined);
    expect(() => parseResearchModel(model, researchIdentity())).toThrow();
  }
  const model = researchFixture(); model.fixtures.push(model.fixtures[0]!);
  expect(() => parseResearchModel(model, researchIdentity())).toThrow();
});

it('returns a metadata snapshot so callers cannot change reviewed identity through the input', () => {
  const model = researchFixture(), parsed = parseResearchModel(model, researchIdentity());
  model.variants[0]!.model.sha256 = 'b'.repeat(64); model.research.selectedUpdate = 1;
  expect(parsed.variants[0]!.model.sha256).toBe('3'.repeat(64));
  expect(parsed.research.selectedUpdate).toBe(256);
});
