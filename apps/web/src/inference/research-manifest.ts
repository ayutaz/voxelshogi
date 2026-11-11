import { assetUrl, type FileRef } from './assets';
import { POLICY_ELEMENTS, type ModelManifest, type TrainedIdentity, type Variant, type Precision } from './manifest';
import { TRAINED_NUMERIC_CONTRACT } from './numeric';

export type ResearchArchitecture = 'full' | 'axial' | 'geometry' | 'cnn';
export interface ResearchIdentity extends TrainedIdentity { profile: 'research-m-v1'; architecture: ResearchArchitecture }
export interface ResearchProvenance {
  schema: 'voxelshogi-research-inference-v1';
  architecture: { architecture: ResearchArchitecture; side: number; width: number; layers: number; heads: number; ffn: number; policy_rank: number };
  trainingSourceCommit: string; trainingBindingSha256: string; selectedUpdate: number; totalUpdates: number;
  selection: FileRef; evaluationProtocolSha256: string; finalRootsSha256: string;
}
export interface ResearchVariant extends Variant {
  evaluation: { scope: 'final-holdout-v1'; complete: true; gameCount: 24; modelSha256: string; weightsSha256: string; report: FileRef };
}
export interface ResearchManifest extends ModelManifest { checkpoint: FileRef; research: ResearchProvenance; variants: ResearchVariant[] }
export const RESEARCH_MODEL_BYTES = 512 * 1024 * 1024;
const METADATA_BYTES = 1024 * 1024;
const COUNTS: Record<ResearchArchitecture, number> = { full: 25_783_688, axial: 25_783_688, geometry: 26_098_120, cnn: 28_606_344 };
const NAMES = ['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b'];
const PRECISIONS: Precision[] = ['fp32', 'fp16', 'int8'];
const HASH = /^[0-9a-f]{64}$/, COMMIT = /^[0-9a-f]{40}$/;
export function isResearchArchitecture(value: unknown): value is ResearchArchitecture { return typeof value === 'string' && Object.hasOwn(COUNTS, value); }
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid research manifest object');
  return value as Record<string, unknown>;
}
function integer(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max;
}
function hash(value: unknown, pattern = HASH): value is string { return typeof value === 'string' && pattern.test(value); }
function descriptor(value: unknown, path: string, maximum: number, bytes?: number): FileRef {
  const f = object(value);
  if (Object.keys(f).length !== 3 || f.path !== path || !integer(f.bytes, 1, maximum) || (bytes !== undefined && f.bytes !== bytes) || !hash(f.sha256)) throw new Error('invalid research artifact descriptor');
  assetUrl('https://asset.invalid/', path);
  return { path, bytes: f.bytes, sha256: f.sha256 };
}
function tensor(value: unknown, expected: readonly number[]) {
  const t = object(value);
  if (t.dtype !== 'float32' || !Array.isArray(t.shape) || t.shape.length !== expected.length || t.shape.some((n, i) => n !== expected[i])) throw new Error('research tensor shape/dtype differs');
}
function keys(value: Record<string, unknown>, names: readonly string[]) {
  if (Object.keys(value).length !== names.length || names.some(name => !Object.hasOwn(value, name))) throw new Error('incomplete research manifest inventory');
}

/** Metadata review only. The catalog pins the entire manifest after Linux
 * publication verifies selection/evaluation files and all payload hashes.
 * Actual backend output comparison remains mandatory in PolicySession.
 */
export function parseResearchModel(value: unknown, identity: ResearchIdentity): ResearchManifest {
  const m = object(value);
  if (identity.profile !== 'research-m-v1' || !isResearchArchitecture(identity.architecture) || identity.license !== 'Apache-2.0' || !hash(identity.sourceCommit, COMMIT)) throw new Error('invalid research release identity');
  if (m.schema !== 1 || m.trained !== true || m.sourceDirty !== false || m.id !== identity.id || typeof m.id !== 'string' || !/^[a-zA-Z0-9._-]{1,128}$/.test(m.id) || m.sourceCommit !== identity.sourceCommit || m.license !== identity.license ||
    m.inputSchema !== 'voxelshogi-standard-features-v1' || m.ruleset !== 'voxelshogi-standard-v1' || m.numericContract !== TRAINED_NUMERIC_CONTRACT ||
    !integer(m.seed, 0, Number.MAX_SAFE_INTEGER) || m.parameters !== COUNTS[identity.architecture]) throw new Error('research model identity/dimensions differ');
  tensor(object(m.inputs).features, [1, 729, 43]);
  tensor(object(m.outputs).policy, [1, POLICY_ELEMENTS]); tensor(object(m.outputs).value, [1, 1]);
  const checkpoint = descriptor(m.checkpoint, 'model.safetensors', RESEARCH_MODEL_BYTES);
  const r = object(m.research), a = object(r.architecture);
  const expected = { architecture: identity.architecture, side: 9, width: identity.architecture === 'cnn' ? 256 : 512, layers: 8, heads: 8, ffn: 2048, policy_rank: 64 };
  keys(a, Object.keys(expected));
  if (Object.entries(expected).some(([key, v]) => a[key] !== v)) throw new Error('research architecture differs from fixed M profile');
  if (r.schema !== 'voxelshogi-research-inference-v1' || !hash(r.trainingSourceCommit, COMMIT) || !hash(r.trainingBindingSha256) ||
    !integer(r.totalUpdates, 1, 1_000_000) || !integer(r.selectedUpdate, 1, r.totalUpdates) || !hash(r.evaluationProtocolSha256) || !hash(r.finalRootsSha256)) throw new Error('incomplete research training/evaluation provenance');
  descriptor(r.selection, 'selection.json', METADATA_BYTES);
  if (!Array.isArray(m.fixtures) || m.fixtures.length !== NAMES.length) throw new Error('research package requires all four fixtures');
  for (let i = 0; i < NAMES.length; i++) {
    const f = object(m.fixtures[i]), name = NAMES[i]!;
    if (f.name !== name || f.side !== (i === 1 ? 'w' : 'b') || object(f.record).ruleset_id !== m.ruleset) throw new Error('research fixture identity differs');
    descriptor(f.input, `inputs/${name}.f32`, 125_388, 125_388);
  }
  if (!Array.isArray(m.variants) || m.variants.length !== PRECISIONS.length) throw new Error('research package requires all three formats');
  for (let i = 0; i < PRECISIONS.length; i++) {
    const v = object(m.variants[i]), precision = PRECISIONS[i]!;
    if (v.id !== precision || v.precision !== precision) throw new Error('research variant identity differs');
    const model = descriptor(v.model, `${precision}.onnx`, RESEARCH_MODEL_BYTES);
    if (precision !== 'fp32') {
      const c = object(v.conversion);
      const tensors = precision === 'fp16' ? c.convertedTensors : c.quantizedTensors;
      const elements = precision === 'fp16' ? c.convertedElements : c.quantizedElements;
      if (c.method !== (precision === 'fp16' ? 'fp16-weight-only' : 'symmetric-per-tensor-weight-only-int8') || c.compute !== 'float32' || c.activations !== 'float32' ||
        !integer(tensors, 1, Number.MAX_SAFE_INTEGER) || !integer(elements, 1, Number(m.parameters))) throw new Error('research format requires evidenced weight-only conversion');
    } else if (Object.hasOwn(v, 'conversion')) throw new Error('research FP32 must remain the unconverted reference');
    const references = object(v.references); keys(references, NAMES);
    for (const name of NAMES) {
      const output = object(references[name]); keys(output, ['policy', 'value']);
      descriptor(output.policy, `reference/${precision}/${name}-policy.f32`, POLICY_ELEMENTS * 4, POLICY_ELEMENTS * 4);
      descriptor(output.value, `reference/${precision}/${name}-value.f32`, 4, 4);
    }
    if (precision !== 'fp32') {
      const differences = object(v.fp32Difference); keys(differences, NAMES);
      for (const name of NAMES) for (const output of ['policy', 'value']) {
        const stats = object(object(differences[name])[output]);
        if (stats.elements !== (output === 'policy' ? POLICY_ELEMENTS : 1) || typeof stats.argmaxEqual !== 'boolean' ||
          ['maxAbs', 'mae', 'rmse', 'maxRelative'].some(key => typeof stats[key] !== 'number' || !Number.isFinite(stats[key]) || stats[key] < 0)) throw new Error('invalid research FP32 difference');
      }
    }
    const evaluation = object(v.evaluation);
    if (evaluation.scope !== 'final-holdout-v1' || evaluation.complete !== true || evaluation.gameCount !== 24 || evaluation.modelSha256 !== model.sha256 || evaluation.weightsSha256 !== checkpoint.sha256) throw new Error('research format lacks bound final evaluation');
    descriptor(evaluation.report, `evaluation/${precision}.json`, METADATA_BYTES);
  }
  return structuredClone(m) as unknown as ResearchManifest;
}
