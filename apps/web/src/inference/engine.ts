import { assetUrl, fetchVerified, type FileRef } from './assets';
import { openBackend, type BackendPort, type Profile, type RuntimeInfo } from './backend';
import { loadPackage, type ModelPackage } from './runtime';
import { POLICY_ELEMENTS, type Backend, type Precision } from './manifest';
import { collectResourceTimings, type AssetTiming } from './resources';

export interface InferenceRequest {
  schema: 1; kind: 'infer'; requestId: number; revision: number; packageHash: string;
  variant: Precision; fixture: string; backend: Backend; iterations: 1 | 40;
}
export interface Comparison { elements: number; maxAbs: number; maxRelative: number; exceeded: number; atol: number; rtol: number }
export interface InferenceResult {
  request: InferenceRequest; value: number; comparison: { policy: Comparison; value: Comparison };
  metrics: { samples: number[]; warmup: number; medianMs: number; p95Ms: number; loadMs: number; initMs: number; totalMs: number; tensorBytes: number; resources: AssetTiming[] };
  information: RuntimeInfo; profile: Profile;
  buffers: { created: number; liveBytes: number; peakBytes: number } | null;
}
interface Dependencies {
  load: () => Promise<ModelPackage>;
  open: (pkg: ModelPackage, backend: Backend, precision: Precision) => Promise<BackendPort>;
  read: (base: string, file: FileRef) => Promise<Uint8Array<ArrayBuffer>>;
  now: () => number;
  resources?: (since: number) => AssetTiming[];
}

export function parseInferenceRequest(value: unknown): InferenceRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid inference request');
  const r = value as Record<string, unknown>;
  const keys = ['schema', 'kind', 'requestId', 'revision', 'packageHash', 'variant', 'fixture', 'backend', 'iterations'];
  if (Object.keys(r).some((key) => !keys.includes(key)) || r.schema !== 1 || r.kind !== 'infer' || typeof r.requestId !== 'number' || !Number.isSafeInteger(r.requestId) || r.requestId <= 0 || typeof r.revision !== 'number' || !Number.isSafeInteger(r.revision) || r.revision < 0 || typeof r.packageHash !== 'string' || !/^[0-9a-f]{64}$/.test(r.packageHash) || !['fp32', 'fp16', 'int8'].includes(String(r.variant)) || typeof r.fixture !== 'string' || !/^[a-z0-9-]{1,64}$/.test(r.fixture) || !['wasm', 'webgpu'].includes(String(r.backend)) || (r.iterations !== 1 && r.iterations !== 40)) throw new Error('invalid inference request fields');
  return r as unknown as InferenceRequest;
}

export function compare(reference: Float32Array, actual: Float32Array, count: number, precision: Precision): Comparison {
  if (reference.length !== count || actual.length !== count) throw new Error('model output length mismatch');
  const [atol, rtol] = precision === 'fp16' ? [1e-3, 1e-2] : [1e-5, 1e-4];
  let maxAbs = 0, maxRelative = 0, exceeded = 0;
  for (let i = 0; i < count; i++) {
    const ref = reference[i]!, value = actual[i]!;
    if (!Number.isFinite(ref) || !Number.isFinite(value)) throw new Error('nonfinite model output');
    const delta = Math.abs(value - ref);
    maxAbs = Math.max(maxAbs, delta); maxRelative = Math.max(maxRelative, delta / Math.max(Math.abs(ref), 1.1754943508222875e-38));
    if (delta > atol! + rtol! * Math.abs(ref)) exceeded++;
  }
  if (exceeded) throw new Error(`${exceeded}/${count} outputs exceed ${precision} tolerance; maxAbs=${maxAbs}; maxRelative=${maxRelative}; atol=${atol}; rtol=${rtol}`);
  return { elements: count, maxAbs, maxRelative, exceeded, atol: atol!, rtol: rtol! };
}

export class InferenceEngine {
  private busy = false;
  private disposed = false;
  private pkg: ModelPackage | null = null;
  private port: BackendPort | null = null;
  private backend: Backend | null = null;
  constructor(private readonly deps: Dependencies = {
    load: () => loadPackage(new URL('/models/m3/index.json', location.origin).href), open: openBackend,
    read: (base, file) => fetchVerified(assetUrl(base, file.path), file), now: () => performance.now(), resources: collectResourceTimings,
  }, private readonly onPhase: (phase: 'loading' | 'initializing' | 'running') => void = () => {}) {}

  async infer(value: unknown): Promise<InferenceResult> {
    if (this.disposed || this.busy) throw new Error(this.disposed ? 'inference engine disposed' : 'inference engine busy');
    const request = parseInferenceRequest(value);
    this.busy = true;
    const start = this.deps.now();
    try {
      this.onPhase('loading');
      const pkg = this.pkg ??= await this.deps.load();
      if (pkg.packageHash !== request.packageHash) throw new Error('obsolete model package');
      const variant = pkg.model.variants.find((v) => v.id === request.variant), fixture = pkg.model.fixtures.find((f) => f.name === request.fixture);
      if (!variant || !fixture) throw new Error('unknown model variant/fixture');
      if (this.backend && this.backend !== request.backend) throw new Error('backend changes require a new Worker');
      this.port ??= await this.deps.open(pkg, request.backend, variant.precision);
      this.backend = request.backend;
      const port = this.port;
      if (request.backend === 'webgpu' && request.variant === 'fp16' && !port.info.features.includes('shader-f16')) throw new Error('shader-f16 is not available');
      const references = variant.references[fixture.name]!;
      const [model, inputBytes, policyBytes, valueBytes] = await Promise.all([
        this.deps.read(pkg.modelBase, variant.model), this.deps.read(pkg.modelBase, fixture.input),
        this.deps.read(pkg.modelBase, references.policy), this.deps.read(pkg.modelBase, references.value),
      ]);
      const features = new Float32Array(inputBytes.buffer, inputBytes.byteOffset, inputBytes.byteLength / 4);
      const refPolicy = new Float32Array(policyBytes.buffer, policyBytes.byteOffset, policyBytes.byteLength / 4);
      const refValue = new Float32Array(valueBytes.buffer, valueBytes.byteOffset, valueBytes.byteLength / 4);
      if (features.length !== 729 * 43 || features.some((n) => !Number.isFinite(n))) throw new Error('invalid model input');
      if (this.disposed) throw new Error('inference engine disposed');
      const loaded = this.deps.now();
      port.resetProfile();
      this.onPhase('initializing');
      const session = await port.createSession(model, variant.precision);
      const initialized = this.deps.now();
      let comparison: InferenceResult['comparison'] | null = null, outputValue = 0;
      const times: number[] = [];
      try {
        this.onPhase('running');
        for (let i = 0; i < request.iterations; i++) {
          const tick = this.deps.now();
          const outputs = await session.run(features);
          times.push(this.deps.now() - tick); // includes CPU readback/GPU completion
          try {
            if (this.disposed) throw new Error('inference engine disposed');
            const current = { policy: compare(refPolicy, outputs.policy, POLICY_ELEMENTS, variant.precision), value: compare(refValue, outputs.value, 1, variant.precision) };
            if (comparison) for (const name of ['policy', 'value'] as const) {
              current[name].maxAbs = Math.max(current[name].maxAbs, comparison[name].maxAbs);
              current[name].maxRelative = Math.max(current[name].maxRelative, comparison[name].maxRelative);
            }
            comparison = current;
            outputValue = outputs.value[0]!;
          } finally { outputs.dispose(); }
        }
      } finally { await session.release(); }
      const profile = port.profile();
      const providers = Object.entries(profile.providers);
      const expected = request.backend === 'webgpu' ? 'WebGpuExecutionProvider' : 'CPUExecutionProvider';
      if (port.info.backend !== request.backend || providers.length === 0 || providers.some(([name, count]) => name !== expected || !Number.isSafeInteger(count) || count <= 0)) throw new Error('unexpected or unverified backend placement');
      const warmup = request.iterations === 40 ? 10 : 0, samples = times.slice(warmup), sorted = [...samples].sort((a, b) => a - b);
      return { request, value: outputValue, comparison: comparison!, information: port.info, profile, buffers: port.buffers?.() ?? null,
        metrics: { samples, warmup, medianMs: (sorted[Math.floor((sorted.length - 1) / 2)]! + sorted[Math.ceil((sorted.length - 1) / 2)]!) / 2, p95Ms: sorted[Math.ceil(sorted.length * .95) - 1]!,
          loadMs: loaded - start, initMs: initialized - loaded, totalMs: this.deps.now() - start, tensorBytes: features.byteLength + POLICY_ELEMENTS * 4 + 4, resources: this.deps.resources?.(start) ?? [] } };
    } finally {
      this.busy = false;
      if (this.disposed) { await this.port?.dispose(); this.port = null; }
    }
  }

  async dispose() {
    if (this.disposed) return;
    this.disposed = true;
    if (!this.busy) { await this.port?.dispose(); this.port = null; }
  }
}
