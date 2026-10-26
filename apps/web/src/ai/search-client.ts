import { parseReply, type SearchInput, type SearchRequest, type SearchSuccess, type WorkerPort } from './search-protocol';

interface Pending {
  request: SearchRequest;
  start: number;
  resolve: (reply: SearchSuccess & { roundTripMs: number }) => void;
  reject: (error: Error) => void;
}
export class SearchClient {
  private worker: WorkerPort | null = null;
  private pending: Pending | null = null;
  private nextId = 1;
  private disposed = false;

  constructor(
    private readonly createWorker: () => WorkerPort = () => new Worker(new URL('./search.worker.ts', import.meta.url), { type: 'module' }),
    private readonly now: () => number = () => performance.now(),
  ) {}

  search(input: SearchInput): Promise<SearchSuccess & { roundTripMs: number }> {
    if (this.disposed) return Promise.reject(new Error('search client disposed'));
    if (this.pending) return Promise.reject(new Error('search client busy'));
    if (!Number.isSafeInteger(this.nextId)) return Promise.reject(new Error('request ID exhausted'));
    const request: SearchRequest = { ...input, requestId: this.nextId++ };
    return new Promise((resolve, reject) => {
      this.pending = { request, resolve, reject, start: this.now() };
      try {
        const worker = this.worker ?? this.createWorker();
        this.worker = worker;
        worker.onmessage = ({ data }: MessageEvent<unknown>) => {
          // A terminated worker's callback may already be queued in the main loop.
          if (this.worker !== worker || !this.pending) return;
          const p = this.pending;
          if (typeof data === 'object' && data !== null && 'requestId' in data && typeof data.requestId === 'number' && Number.isSafeInteger(data.requestId) && data.requestId > 0 && data.requestId !== p.request.requestId) return;
          try {
            const reply = parseReply(data, p.request);
            if (reply.kind === 'error') { this.fail(new Error(`${reply.code}: ${reply.message}`)); return; }
            this.pending = null;
            p.resolve({ ...reply, roundTripMs: this.now() - p.start });
          } catch (error) {
            this.fail(new Error(`search protocol: ${error instanceof Error ? error.message : String(error)}`));
          }
        };
        worker.onerror = (event) => {
          event.preventDefault();
          if (this.worker === worker) this.fail(new Error(event.message || 'Worker failed'));
        };
        worker.onmessageerror = () => { if (this.worker === worker) this.fail(new Error('Worker message decode failed')); };
        worker.postMessage(request);
      } catch (error) { this.fail(error instanceof Error ? error : new Error(String(error))); }
    });
  }

  private fail(error: Error): void {
    const p = this.pending;
    this.pending = null;
    this.closeWorker();
    p?.reject(error);
  }
  private closeWorker(): void {
    const w = this.worker;
    this.worker = null;
    if (w) { w.onmessage = null; w.onerror = null; w.onmessageerror = null; w.terminate(); }
  }
  cancel(): void {
    const error = new Error('search cancelled');
    error.name = 'AbortError';
    this.fail(error);
  }
  dispose(): void { this.disposed = true; this.cancel(); }
}
