import { AUTOMATIC_POLICY, isAutomaticSubmission, type AutomaticSubmission } from './automatic-contract';
import { MAX_GAME_BYTES } from './contract';

export type StartConditions = Pick<AutomaticSubmission, 'mode' | 'selectedAgents'>;
interface Game {
  id: string; owned: boolean; minimumMoves: number; version: number; progressWrites: number; terminal: boolean;
  latest: AutomaticSubmission['record'] | null; conditions: StartConditions | null; queued: string;
}
interface Pending { gameId: string; requestId: string; version: number; body: string; attempts: number }
const newGame = (owned: boolean, minimumMoves = 0): Game => ({ id: crypto.randomUUID(), owned, minimumMoves, version: 0, progressWrites: 0,
  terminal: false, latest: null, conditions: null, queued: '' });

/** No UI state. One in-flight immutable request; bounded latest-snapshot queue. */
export class AutomaticCollection {
  readonly ready: Promise<void>;
  private game = newGame(true);
  private commit = '';
  private enabled = false;
  private disposed = false;
  private pending = new Map<string, Pending>();
  private staged = new Map<string, Game>();
  private active: Pending | null = null;
  private abort: AbortController | null = null;
  private metadataAbort = new AbortController();
  private metadataRetry: ReturnType<typeof setTimeout> | null = null;
  private metadataWake: (() => void) | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private interval: ReturnType<typeof setInterval>;
  constructor(private fetcher: typeof fetch = fetch.bind(globalThis)) {
    this.ready = this.initialize();
    this.interval = setInterval(() => this.flush(), 30000);
  }
  get gameId() { return this.game.id; }
  private async initialize() {
    for (let attempt=0;attempt<4&&!this.disposed;attempt++) {
      const abort = new AbortController(); this.metadataAbort = abort;
      const timeout = setTimeout(() => abort.abort(),10000);
      try {
        const read = async (url: string) => {
          const response = await this.fetcher(url, { signal: abort.signal, credentials: 'omit', cache: 'no-store', redirect: 'error' });
          if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('metadata');
          return response.json();
        };
        const [config, build] = await Promise.all([read('/api/collection'), read('/build-info.json')]);
        if (this.disposed || config?.enabled === false) return;
        if (config?.enabled !== true || config?.policy !== AUTOMATIC_POLICY || !Array.isArray(config.schemas) || !config.schemas.includes(2) || typeof build?.commit !== 'string' || !/^[0-9a-f]{40}$/.test(build.commit)) throw new Error('metadata');
        this.commit = build.commit; this.enabled = true;
        for (const [id, game] of this.staged) { this.staged.delete(id); this.enqueue(game, true); }
        this.flush();
        return;
      } catch { /* Collection never blocks or changes the game. */ }
      finally { clearTimeout(timeout); }
      if (this.disposed || attempt === 3) return;
      await new Promise<void>(resolve => {
        this.metadataWake = resolve;
        this.metadataRetry = setTimeout(() => { this.metadataRetry = null; this.metadataWake = null; resolve(); },[2000,8000,30000][attempt]!);
      });
    }
  }
  observe(recordJson: string, conditions: StartConditions) {
    const g = this.game;
    if (this.disposed || !g.owned || g.terminal) return;
    try {
      const record: unknown = JSON.parse(recordJson);
      const candidate = { schema: 2, policy: AUTOMATIC_POLICY, gameId: g.id, requestId: g.id, version: 1,
        state: 'progress', applicationCommit: this.commit || '0'.repeat(40), conditionsScope: 'game-start',
        ...(g.conditions ?? conditions), record };
      if (record && typeof record === 'object' && 'result' in record && record.result !== null) candidate.state = 'finished';
      else if (record && typeof record === 'object' && 'termination' in record && record.termination === 'Abandoned') candidate.state = 'aborted';
      if (!isAutomaticSubmission(candidate) || new TextEncoder().encode(JSON.stringify(candidate)).length > MAX_GAME_BYTES) return;
      if (candidate.record.moves.length <= g.minimumMoves) return;
      g.conditions ??= structuredClone(conditions);
      g.latest = candidate.record;
      if (g.version === 0 || candidate.state !== 'progress') this.flush();
    } catch { /* Malformed/imported/oversize data is not sent. */ }
  }
  /** Called before a store replacement; the previous game keeps its own frozen ID/body. */
  begin(owned: boolean, minimumMoves = 0) {
    if (!this.enabled && this.game.owned && this.game.latest) {
      if (this.staged.size >= 8) this.staged.delete(this.staged.keys().next().value!);
      this.staged.set(this.game.id, this.game);
    } else this.flush(true);
    this.game = newGame(owned, minimumMoves);
  }
  flush(abandoned = false) {
    this.enqueue(this.game, abandoned);
  }
  private enqueue(g: Game, abandoned: boolean) {
    if (this.disposed || !this.enabled || !g.owned || !g.latest || !g.conditions || g.terminal) return;
    const record = structuredClone(g.latest);
    const state = record.result !== null ? 'finished' : record.termination === 'Abandoned' || abandoned ? 'aborted' : 'progress';
    if (state === 'aborted') { record.result = null; record.termination = 'Abandoned'; }
    const signature = JSON.stringify({ state, record });
    if (signature === g.queued || (state === 'progress' && g.progressWrites >= 128)) return;
    const value: AutomaticSubmission = { schema: 2, policy: AUTOMATIC_POLICY, gameId: g.id, requestId: crypto.randomUUID(),
      version: g.version + 1, state, applicationCommit: this.commit, conditionsScope: 'game-start', ...g.conditions, record };
    const body = JSON.stringify(value);
    if (!isAutomaticSubmission(value) || new TextEncoder().encode(body).length > MAX_GAME_BYTES) return;
    g.version++; g.queued = signature; g.terminal = state !== 'progress';
    if (state === 'progress') g.progressWrites++;
    // At most 8 pending games (2 MiB), in addition to the single active request.
    if (!this.pending.has(g.id) && this.pending.size >= 8) this.pending.delete(this.pending.keys().next().value!);
    this.pending.set(g.id, { gameId: g.id, requestId: value.requestId, version: value.version, body, attempts: 0 });
    this.drain();
  }
  private drain() {
    if (this.disposed || this.active || this.retry) return;
    const next = this.pending.entries().next().value;
    if (!next) return;
    this.pending.delete(next[0]); this.active = next[1];
    void this.transmit(next[1]);
  }
  private async transmit(p: Pending) {
    if (this.disposed) return;
    const abort = new AbortController(); this.abort = abort;
    const timeout = setTimeout(() => abort.abort(), 10000);
    let acknowledged = false, retryable = true;
    try {
      const response = await this.fetcher('/api/games', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: p.body, signal: abort.signal, credentials: 'omit', cache: 'no-store', redirect: 'error',
        keepalive: new TextEncoder().encode(p.body).length <= 60 * 1024 });
      retryable = response.status >= 500 || response.status === 408 || response.ok;
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('response');
      const ack = await response.json();
      acknowledged = ack?.gameId === p.gameId && ack?.requestId === p.requestId && Number.isSafeInteger(ack?.version) && ack.version >= p.version && ['received_unverified', 'verified', 'rejected'].includes(ack?.status);
    } catch { /* Same immutable body is retried; never log the payload. */ }
    finally { clearTimeout(timeout); if (this.abort === abort) this.abort = null; }
    if (this.disposed) return;
    if (!acknowledged && retryable && p.attempts < 3) {
      const delay = [2000, 8000, 30000][p.attempts++]!;
      this.retry = setTimeout(() => { this.retry = null; void this.transmit(p); }, delay);
    } else { this.active = null; this.drain(); }
  }
  dispose() {
    this.disposed = true; clearInterval(this.interval); if (this.retry) clearTimeout(this.retry);
    if (this.metadataRetry) clearTimeout(this.metadataRetry); this.metadataWake?.();
    this.metadataAbort.abort(); this.abort?.abort(); this.pending.clear(); this.staged.clear(); this.game.latest = null;
  }
}
