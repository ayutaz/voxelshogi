import { parsePolicyRequest, parsePolicyResponse, type ModelFile, type PolicyPhase, type PolicyRequest, type PolicySuccess } from './policy-protocol';
import { parsePolicySelection, type PolicyPosition, type PolicySelection } from './policy-session';

export interface PolicyWorkerPort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  onerror: ((event: ErrorEvent) => void) | null;
  onmessageerror: ((event: MessageEvent) => void) | null;
  postMessage: (request: PolicyRequest) => void;
  terminate: () => void;
}
export interface PolicySource { selection: PolicySelection; files: ModelFile[]; fixtures: string[]; fp16WeightOnly?: boolean }
export type PolicyClientResult = PolicySuccess & { roundTripMs: number };
interface Pending { request: PolicyRequest; start: number; resolve: (reply: PolicyClientResult) => void; reject: (error: Error) => void; progress?: (phase: PolicyPhase) => void }

/** One identity per client/Worker; File bodies are read only inside the Worker. */
export class PolicyClient {
  private readonly source: PolicySource;
  private worker: PolicyWorkerPort | null = null;
  private pending: Pending | null = null;
  private nextId = 1;
  private ready = false;
  private disposed = false;
  constructor(source: PolicySource,
    private readonly createWorker: () => PolicyWorkerPort = () => new Worker(new URL('./policy.worker.ts', import.meta.url), { type: 'module' }),
    private readonly now = () => performance.now()) {
    if (source.fixtures.length < 1 || source.fixtures.length > 32 || new Set(source.fixtures).size !== source.fixtures.length || source.fixtures.some(name => !/^[a-z0-9-]{1,64}$/.test(name))) throw new Error('invalid expected policy fixtures');
    if (source.fp16WeightOnly !== undefined && typeof source.fp16WeightOnly !== 'boolean') throw new Error('invalid expected policy precision');
    this.source = { selection: parsePolicySelection(source.selection), files: source.files.map(entry => ({ ...entry })), fixtures: [...source.fixtures], fp16WeightOnly: source.fp16WeightOnly ?? false };
  }
  bestMove(root: PolicyPosition, progress?: Pending['progress']): Promise<PolicyClientResult> {
    if (this.disposed) return Promise.reject(new Error('policy client disposed'));
    if (this.pending) return Promise.reject(new Error('policy client busy'));
    if (!Number.isSafeInteger(this.nextId)) return Promise.reject(new Error('policy request ID exhausted'));
    let request: PolicyRequest;
    try { request = parsePolicyRequest({ schema: 1, kind: 'policy', requestId: this.nextId++, selection: this.source.selection, root, ...(this.ready ? {} : { files: this.source.files }) }); }
    catch (error) { return Promise.reject(error); }
    return new Promise((resolve, reject) => {
      this.pending = { request, start: this.now(), resolve, reject, progress };
      try {
        const worker = this.worker ?? this.createWorker(); this.worker = worker;
        worker.onmessage = ({ data }) => {
          if (this.worker !== worker || !this.pending) return;
          const pending = this.pending;
          if (data && typeof data === 'object' && 'requestId' in data && typeof data.requestId === 'number' && Number.isSafeInteger(data.requestId) && data.requestId > 0 && data.requestId !== pending.request.requestId) return;
          try {
            const reply = parsePolicyResponse(data, pending.request, this.source.fixtures, this.source.fp16WeightOnly);
            if (reply.kind === 'progress') { pending.progress?.(reply.phase); return; }
            if (reply.kind === 'error') { this.fail(new Error(`${reply.code}: ${reply.message}`)); return; }
            this.ready = true; this.pending = null;
            pending.resolve({ ...reply, roundTripMs: this.now() - pending.start });
          } catch (error) { this.fail(new Error(`policy protocol: ${error instanceof Error ? error.message : String(error)}`)); }
        };
        worker.onerror = event => { event.preventDefault(); if (this.worker === worker) this.fail(new Error(event.message || 'policy Worker failed')); };
        worker.onmessageerror = () => { if (this.worker === worker) this.fail(new Error('policy Worker message decode failed')); };
        worker.postMessage(request);
      } catch (error) { this.fail(error instanceof Error ? error : new Error(String(error))); }
    });
  }
  private close() {
    const worker = this.worker; this.worker = null; this.ready = false;
    if (worker) { worker.onmessage = null; worker.onerror = null; worker.onmessageerror = null; worker.terminate(); }
  }
  private fail(error: Error) { const pending = this.pending; this.pending = null; this.close(); pending?.reject(error); }
  cancel() { const error = new Error('policy cancelled'); error.name = 'AbortError'; this.fail(error); }
  dispose() { this.disposed = true; this.cancel(); }
}
