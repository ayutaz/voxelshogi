import { assetUrl, type FileRef } from './assets';

export const POLICY_ELEMENTS = 1_067_985;
export type Precision = 'fp32' | 'fp16' | 'int8';
export type Backend = 'wasm' | 'webgpu';
export interface ModelFixture { name: string; side: 'b' | 'w'; record: Record<string, unknown>; input: FileRef }
export interface Difference { elements: number; maxAbs: number; mae: number; rmse: number; maxRelative: number; argmaxEqual: boolean }
export interface Variant { id: Precision; precision: Precision; model: FileRef; references: Record<string, { policy: FileRef; value: FileRef }>; fp32Difference?: Record<string, { policy: Difference; value: Difference }> }
export interface ModelManifest {
  schema: 1; id: string; trained: false; license: string | null; inputSchema: string; ruleset: string;
  seed: number; parameters: number; fixtures: ModelFixture[]; variants: Variant[];
}
export interface RuntimeManifest { version: string; bundle: FileRef; bootstrap: FileRef; wasm: FileRef & { parts: FileRef[] }; notices: FileRef[] }
export interface Deployment { schema: 1; publication: boolean; model: FileRef; modelNotices: FileRef[]; runtime: RuntimeManifest }

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid manifest object');
  return value as Record<string, unknown>;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 32) throw new Error('invalid manifest list');
  return value;
}
function file(value: unknown): FileRef {
  const f = record(value);
  if (typeof f.path !== 'string' || typeof f.bytes !== 'number' || !Number.isSafeInteger(f.bytes) || f.bytes < 1 || f.bytes > 64 * 1024 * 1024 || typeof f.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(f.sha256)) throw new Error('invalid manifest file');
  assetUrl('https://asset.invalid/', f.path);
  return f as unknown as FileRef;
}
function shape(value: unknown, expected: number[]) {
  const tensor = record(value);
  if (tensor.dtype !== 'float32' || !Array.isArray(tensor.shape) || tensor.shape.length !== expected.length || tensor.shape.some((n, i) => n !== expected[i])) throw new Error('tensor shape/dtype mismatch');
}

export function parseModel(value: unknown, publication = true): ModelManifest {
  const m = record(value);
  if (m.schema !== 1 || m.inputSchema !== 'voxelshogi-standard-features-v1' || m.ruleset !== 'voxelshogi-standard-v1' || m.trained !== false || typeof m.id !== 'string' || !/^[a-zA-Z0-9._-]{1,128}$/.test(m.id)) throw new Error('unsupported model manifest');
  if (publication && m.license !== 'Apache-2.0') throw new Error('model publication license is not approved');
  if (typeof m.parameters !== 'number' || !Number.isSafeInteger(m.parameters) || m.parameters < 5_000_000 || m.parameters > 10_000_000 || typeof m.seed !== 'number' || !Number.isSafeInteger(m.seed)) throw new Error('invalid model size/seed');
  shape(record(m.inputs).features, [1, 729, 43]);
  shape(record(m.outputs).policy, [1, POLICY_ELEMENTS]); shape(record(m.outputs).value, [1, 1]);
  const fixtures = array(m.fixtures).map((item) => {
    const f = record(item);
    if (typeof f.name !== 'string' || !/^[a-z0-9-]{1,64}$/.test(f.name) || (f.side !== 'b' && f.side !== 'w') || record(f.record).ruleset_id !== m.ruleset || file(f.input).bytes !== 125388) throw new Error('invalid model fixture');
    return f as unknown as ModelFixture;
  });
  const names = fixtures.map((f) => f.name);
  if (new Set(names).size !== names.length) throw new Error('duplicate model fixture');
  const variants = array(m.variants).map((item) => {
    const v = record(item);
    if (!['fp32', 'fp16', 'int8'].includes(String(v.id)) || v.precision !== v.id) throw new Error('unsupported model precision');
    file(v.model);
    const references = record(v.references);
    if (Object.keys(references).length !== names.length || !names.every((name) => Object.hasOwn(references, name))) throw new Error('incomplete model references');
    for (const outputs of Object.values(references)) {
      const r = record(outputs);
      if (file(r.policy).bytes !== POLICY_ELEMENTS * 4 || file(r.value).bytes !== 4) throw new Error('reference byte length mismatch');
    }
    if (v.precision !== 'fp32') {
      const differences = record(v.fp32Difference);
      if (Object.keys(differences).length !== names.length || !names.every(name => Object.hasOwn(differences, name))) throw new Error('incomplete FP32 differences');
      for (const outputs of Object.values(differences)) for (const name of ['policy', 'value'] as const) {
        const stats = record(record(outputs)[name]);
        if (stats.elements !== (name === 'policy' ? POLICY_ELEMENTS : 1) || typeof stats.argmaxEqual !== 'boolean' || ['maxAbs', 'mae', 'rmse', 'maxRelative'].some(key => typeof stats[key] !== 'number' || !Number.isFinite(stats[key]) || stats[key] < 0)) throw new Error('invalid FP32 difference');
      }
    }
    return v as unknown as Variant;
  });
  if (new Set(variants.map((v) => v.id)).size !== variants.length) throw new Error('duplicate model variant');
  return { ...m, fixtures, variants } as unknown as ModelManifest;
}

export function parseDeployment(value: unknown, allowLocal = false): Deployment {
  const index = record(value);
  if (index.schema !== 1 || typeof index.publication !== 'boolean' || (!index.publication && !allowLocal)) throw new Error('unapproved inference publication');
  if (file(index.model).bytes > 1024 * 1024) throw new Error('oversized model manifest');
  const modelNotices = index.modelNotices ?? [];
  if (!Array.isArray(modelNotices) || modelNotices.length > 32 || (index.publication && modelNotices.length < 2)) throw new Error('model license and card notices are required');
  modelNotices.forEach(file);
  const runtime = record(index.runtime);
  if (runtime.version !== '1.31.1') throw new Error('runtime version mismatch');
  file(runtime.bundle); file(runtime.bootstrap);
  const wasm = file(runtime.wasm), parts = array(record(runtime.wasm).parts).map(file);
  if (parts.reduce((n, p) => n + p.bytes, 0) !== wasm.bytes || new Set(parts.map((p) => p.path)).size !== parts.length) throw new Error('incomplete runtime parts');
  array(runtime.notices).forEach(file);
  return { ...index, modelNotices } as unknown as Deployment;
}
