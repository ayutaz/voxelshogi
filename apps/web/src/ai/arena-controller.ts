import { GameStore } from '../game/store';
import { SearchClient } from './search-client';
import type { SearchConfig, SearchSuccess } from './search-protocol';

export type ArenaMode = 'r-r' | 'h-r' | 'r-h';
export interface ArenaOptions {
  mode: ArenaMode;
  running: boolean;
  bDifficulty: 'easy' | 'normal';
  wDifficulty: 'easy' | 'normal';
  delayMs: number;
  limits: SearchConfig;
  seed: number;
}
export const DEFAULT_AI_OPTIONS: ArenaOptions = {
  mode: 'r-r', running: false, bDifficulty: 'normal', wDifficulty: 'normal', delayMs: 400,
  limits: { maxDepth: 6, maxNodes: 50_000, maxTimeMs: 1000 }, seed: 42,
};
type Completed = SearchSuccess & { roundTripMs: number };
export interface AiStatus {
  phase: 'paused' | 'waiting' | 'thinking' | 'human' | 'history' | 'finished' | 'error';
  error: string | null;
  last: Completed | null;
}
type Client = Pick<SearchClient, 'search' | 'cancel' | 'dispose'>;

/** Owns asynchronous turn scheduling; React only renders state and sends actions. */
export class ArenaController {
  private options = { ...DEFAULT_AI_OPTIONS };
  private key = this.searchKey(this.options);
  private state: AiStatus = { phase: 'paused', error: null, last: null };
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private scheduledSingle = false;
  private pending = false;
  private generation = 0;
  private disposed = false;
  private suspended = false;
  private applying = false;
  private retryStep = false;
  private readonly unsubscribe: () => void;

  constructor(private readonly store: GameStore, private readonly client: Client = new SearchClient()) {
    this.unsubscribe = store.subscribe(() => {
      if (this.applying || this.disposed) return;
      this.invalidate();
      this.state = { ...this.state, last: null, error: null };
      this.schedule();
    });
    this.schedule();
  }
  snapshot = (): AiStatus => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  private publish(phase: AiStatus['phase']): void {
    this.state = { ...this.state, phase };
    for (const listener of this.listeners) listener();
  }
  private searchKey(o: ArenaOptions): string {
    return JSON.stringify([o.mode, o.running, o.bDifficulty, o.wDifficulty, o.limits, o.seed]);
  }
  configure(options: ArenaOptions): void {
    if (this.disposed) return;
    const key = this.searchKey(options);
    const delayChanged = this.options.delayMs !== options.delayMs;
    this.options = { ...options, limits: { ...options.limits } };
    if (key !== this.key) {
      this.key = key;
      this.invalidate();
      this.state = { ...this.state, error: null };
      this.schedule();
    } else if (delayChanged && this.timer !== null && !this.scheduledSingle) {
      this.invalidate();
      this.schedule();
    }
  }
  pause(): void {
    if (this.options.running) this.configure({ ...this.options, running: false });
    else { this.invalidate(); this.schedule(); }
  }
  suspend(): void { this.suspended = true; this.invalidate(); this.schedule(); }
  resume(): void { this.suspended = false; this.schedule(); }
  step(): boolean {
    const s = this.store.snapshot();
    if (this.disposed || this.suspended || this.options.running || this.pending || this.timer !== null || s.finished || this.human() || this.state.error) return false;
    this.schedule(true);
    return true;
  }
  retry(): void {
    if (this.disposed || !this.state.error) return;
    this.state = { ...this.state, error: null };
    this.schedule(this.retryStep);
  }
  private human(): boolean {
    const side = this.store.snapshot().side;
    return (this.options.mode === 'h-r' && side === 'b') || (this.options.mode === 'r-h' && side === 'w');
  }
  private invalidate(): void {
    this.generation += 1;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.scheduledSingle = false;
    if (this.pending) this.client.cancel();
    this.pending = false;
  }
  private schedule(single = false): void {
    if (this.disposed || this.pending || this.timer !== null) return;
    const s = this.store.snapshot();
    if (s.finished) { this.publish('finished'); return; }
    if (this.human()) { this.publish('human'); return; }
    if (this.state.error) { this.publish('error'); return; }
    if (this.suspended || (!this.options.running && !single)) { this.publish('paused'); return; }
    if (s.ply !== s.moveCount && !single) { this.publish('history'); return; }
    const generation = this.generation;
    this.scheduledSingle = single;
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.disposed || generation !== this.generation) return;
      this.pending = true;
      this.retryStep = single;
      this.publish('thinking');
      const root = this.store.searchState();
      const difficulty = root.side === 'b' ? this.options.bDifficulty : this.options.wDifficulty;
      void this.client.search({ ...root, schema: 1, kind: 'search', difficulty,
        seed: (this.options.seed + root.revision) >>> 0, limits: this.options.limits }).then((reply) => {
        if (this.disposed || generation !== this.generation) return;
        this.pending = false;
        this.applying = true;
        let error: string | null = null;
        try {
          if (reply.result.bestMove === null) error = '探索が指し手を返しませんでした';
          else {
            const applied = this.store.applyAiMove(reply, reply.result.bestMove);
            if (!applied.ok) error = applied.error;
          }
        } finally { this.applying = false; }
        this.state = { ...this.state, last: reply, error };
        this.schedule();
      }).catch((error: unknown) => {
        if (this.disposed || generation !== this.generation) return;
        this.pending = false;
        this.state = { ...this.state, error: error instanceof Error ? error.message : String(error) };
        this.publish('error');
      });
    }, single ? 0 : this.options.delayMs);
    this.publish('waiting');
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.unsubscribe();
    this.invalidate();
    this.client.dispose();
    this.listeners.clear();
  }
}
