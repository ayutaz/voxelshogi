import { parseInferenceRequest, type InferenceRequest, type InferenceResult } from './engine';
import { POLICY_ELEMENTS } from './manifest';

export type Phase = 'loading' | 'initializing' | 'running';
export interface InferenceWorkerPort {
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: ErrorEvent) => void) | null;
  onmessageerror: ((event: MessageEvent) => void) | null;
  postMessage(message: InferenceRequest): void;
  terminate(): void;
}
export type InferenceInput = Omit<InferenceRequest, 'schema' | 'kind' | 'requestId'>;
export type ClientResult = InferenceResult & { roundTripMs: number };
interface Pending { request: InferenceRequest; start: number; resolve: (r: ClientResult) => void; reject: (e: Error) => void; progress?: (p: Phase, atUnixMs: number) => void }
const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n) && n >= 0;
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('expected object');
  return value as Record<string, unknown>;
}
function validateResult(value: unknown, request: InferenceRequest): InferenceResult {
  const result = record(value), metrics = record(result.metrics), info = record(result.information);
  if (typeof result.value !== 'number' || !Number.isFinite(result.value) || Math.abs(result.value) > 1) throw new Error('invalid Value output');
  const comparison = record(result.comparison);
  for (const name of ['policy', 'value'] as const) {
    const item = record(comparison[name]);
    const [atol, rtol] = request.variant === 'fp16' ? [1e-3, 1e-2] : [1e-5, 1e-4];
    if (item.elements !== (name === 'policy' ? POLICY_ELEMENTS : 1) || item.exceeded !== 0 || !finite(item.maxAbs) || !finite(item.maxRelative) || item.atol !== atol || item.rtol !== rtol) throw new Error('invalid numeric comparison');
  }
  if (!Array.isArray(metrics.samples) || metrics.samples.length !== (request.iterations === 40 ? 30 : 1) || !metrics.samples.every(finite) || metrics.warmup !== (request.iterations === 40 ? 10 : 0)) throw new Error('invalid timing samples');
  for (const field of ['medianMs', 'p95Ms', 'loadMs', 'initMs', 'totalMs']) if (!finite(metrics[field])) throw new Error('invalid timing');
  if (!Array.isArray(metrics.resources) || metrics.resources.length > 256) throw new Error('invalid asset timings');
  for (const item of metrics.resources) {
    const resource = record(item);
    if (typeof resource.url !== 'string' || resource.url.length > 2048 || typeof resource.protocol !== 'string' || typeof resource.delivery !== 'string' || ['startMs', 'durationMs', 'transferBytes', 'encodedBytes', 'decodedBytes'].some(key => !finite(resource[key]))) throw new Error('invalid asset timing');
  }
  if (metrics.tensorBytes !== 4397332 || info.backend !== request.backend || !finite(info.runtimeBytes) || info.runtimeBytes === 0 || !Array.isArray(info.features) || !info.features.every((v) => typeof v === 'string')) throw new Error('invalid backend information');
  const profile = record(result.profile), providers = Object.entries(record(profile.providers));
  const expectedProvider = request.backend === 'webgpu' ? 'WebGpuExecutionProvider' : 'CPUExecutionProvider';
  if (providers.length !== 1 || providers.some(([name, count]) => name !== expectedProvider || !Number.isSafeInteger(count) || Number(count) <= 0)) throw new Error('invalid execution provider evidence');
  return result as unknown as InferenceResult;
}

export class InferenceClient {
  private worker: InferenceWorkerPort | null = null;
  private pending: Pending | null = null;
  private nextId = 1;
  private disposed = false;
  constructor(private readonly createWorker: () => InferenceWorkerPort = () => new Worker(new URL('./inference.worker.ts', import.meta.url), { type: 'module' }), private readonly now = () => performance.now()) {}

  infer(input: InferenceInput, progress?: Pending['progress']): Promise<ClientResult> {
    if (this.disposed) return Promise.reject(new Error('inference client disposed'));
    if (this.pending) return Promise.reject(new Error('inference client busy'));
    let request: InferenceRequest;
    try { request = parseInferenceRequest({ ...input, schema: 1, kind: 'infer', requestId: this.nextId++ }); }
    catch (error) { return Promise.reject(error); }
    return new Promise((resolve, reject) => {
      this.pending = { request, resolve, reject, progress, start: this.now() };
      try {
        const worker = this.worker ?? this.createWorker(); this.worker = worker;
        worker.onmessage = ({ data }: MessageEvent<unknown>) => {
          if (this.worker !== worker || !this.pending) return;
          const pending = this.pending;
          try {
            const message = record(data), root = record(message.kind === 'result' ? record(message.result).request : message.request);
            if (typeof root.requestId === 'number' && Number.isSafeInteger(root.requestId) && root.requestId > 0 && root.requestId !== pending.request.requestId) return;
            const received = parseInferenceRequest(root);
            if ((Object.keys(pending.request) as (keyof InferenceRequest)[]).some((key) => received[key] !== pending.request[key])) throw new Error('inference root mismatch');
            if (message.kind === 'progress') {
              if (!['loading', 'initializing', 'running'].includes(String(message.phase)) || !finite(message.atUnixMs)) throw new Error('invalid progress');
              pending.progress?.(message.phase as Phase, message.atUnixMs); return;
            }
            if (message.kind === 'error') {
              if (typeof message.message !== 'string' || !message.message || message.message.length > 500) throw new Error('invalid error reply');
              this.fail(new Error(message.message)); return;
            }
            if (message.kind !== 'result') throw new Error('unknown inference message');
            const result = validateResult(message.result, pending.request);
            this.pending = null; pending.resolve({ ...result, roundTripMs: this.now() - pending.start });
          } catch (error) { this.fail(new Error(`inference protocol: ${error instanceof Error ? error.message : String(error)}`)); }
        };
        worker.onerror = (event) => { event.preventDefault(); if (this.worker === worker) this.fail(new Error(event.message || 'inference Worker failed')); };
        worker.onmessageerror = () => { if (this.worker === worker) this.fail(new Error('inference Worker message decode failed')); };
        worker.postMessage(request);
      } catch (error) { this.fail(error instanceof Error ? error : new Error(String(error))); }
    });
  }
  private close() { const worker = this.worker; this.worker = null; if (worker) { worker.onmessage = null; worker.onerror = null; worker.onmessageerror = null; worker.terminate(); } }
  private fail(error: Error) { const pending = this.pending; this.pending = null; this.close(); pending?.reject(error); }
  cancel() { const error = new Error('inference cancelled'); error.name = 'AbortError'; this.fail(error); }
  dispose() { this.disposed = true; this.cancel(); }
}
