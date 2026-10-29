import type { GameStore, Snapshot } from '../game/store';
import type { SearchClient } from './search-client';
import type { SearchConfig, SearchInput, SearchSuccess } from './search-protocol';
import { ArenaClient } from './arena-client';
import { modelSeatKey, type ModelCompleted, type ModelDecision, type ModelSeat } from './arena-model';

export type ArenaMode = 'r-r' | 'h-r' | 'r-h';
export type ArenaDifficulty = 'easy' | 'normal' | 'model';
export interface ArenaOptions {
  mode: ArenaMode;
  running: boolean;
  bDifficulty: ArenaDifficulty;
  wDifficulty: ArenaDifficulty;
  bModel?: ModelSeat;
  wModel?: ModelSeat;
  delayMs: number;
  limits: SearchConfig;
  seed: number;
}
export const DEFAULT_AI_OPTIONS: ArenaOptions = {
  mode: 'r-r', running: false, bDifficulty: 'normal', wDifficulty: 'normal', delayMs: 400,
  limits: { maxDepth: 6, maxNodes: 50_000, maxTimeMs: 1000 }, seed: 42,
};
type Completed = (SearchSuccess & { roundTripMs: number }) | ModelCompleted;
export interface AiStatus {
  phase: 'paused' | 'waiting' | 'thinking' | 'human' | 'history' | 'finished' | 'error';
  error: string | null;
  last: Completed | null;
}
type Client = Pick<SearchClient, 'search' | 'cancel' | 'dispose'> & {
  policy?: (input: ModelDecision) => Promise<ModelCompleted>;
  retainModels?: (seats: readonly ModelSeat[]) => void;
};
type Store = Pick<GameStore, 'subscribe' | 'searchState' | 'applyAiMove'> & { snapshot: () => Pick<Snapshot, 'finished' | 'side' | 'ply' | 'moveCount'> };

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

  constructor(private readonly store: Store, private readonly client: Client = new ArenaClient()) {
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
    return JSON.stringify([o.mode, o.running, o.bDifficulty, o.wDifficulty, o.limits, o.seed,
      o.bDifficulty === 'model' && o.bModel ? modelSeatKey(o.bModel) : null,
      o.wDifficulty === 'model' && o.wModel ? modelSeatKey(o.wModel) : null]);
  }
  private retainModels(): void {
    const seats: ModelSeat[] = [];
    if (this.options.mode !== 'h-r' && this.options.bDifficulty === 'model' && this.options.bModel) seats.push(this.options.bModel);
    if (this.options.mode !== 'r-h' && this.options.wDifficulty === 'model' && this.options.wModel) seats.push(this.options.wModel);
    this.client.retainModels?.(seats);
  }
  configure(options: ArenaOptions): void {
    if (this.disposed) return;
    const key = this.searchKey(options);
    const delayChanged = this.options.delayMs !== options.delayMs;
    this.options = { ...options, limits: { ...options.limits } };
    if (key !== this.key) {
      this.key = key;
      this.invalidate();
      this.retainModels();
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
  private decide(input: Omit<SearchInput, 'difficulty'> & { difficulty: ArenaDifficulty }): Promise<Completed> {
    if (input.difficulty !== 'model') return this.client.search({ ...input, difficulty: input.difficulty });
    const model = input.side === 'b' ? this.options.bModel : this.options.wModel;
    if (!model || !this.client.policy) return Promise.reject(new Error('学習済みモデルを選択してください'));
    const { revision, cursor, side, hash, ruleset, recordJson } = input;
    return this.client.policy({ root: { revision, cursor, side, hash, ruleset, recordJson }, model });
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
      void this.decide({ ...root, schema: 1, kind: 'search', difficulty,
        seed: (this.options.seed + root.revision) >>> 0, limits: this.options.limits }).then((reply) => {
        if (this.disposed || generation !== this.generation) return;
        this.pending = false;
        this.applying = true;
        let error: string | null = null;
        try {
          const expected = root.side === 'b' ? this.options.bModel : this.options.wModel;
          if (reply.kind === 'model-result' && (difficulty !== 'model' || !expected || modelSeatKey(expected) !== modelSeatKey(reply.model))) error = 'モデルの応答条件が選択中の設定と一致しません';
          else if (reply.kind !== 'model-result' && difficulty === 'model') error = 'モデルの応答を確認できません';
          else if (reply.result.bestMove === null) error = difficulty === 'model' ? 'モデルが指し手を返しませんでした' : '探索が指し手を返しませんでした';
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
