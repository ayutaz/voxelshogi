import { SearchClient } from './search-client';
import type { SearchInput } from './search-protocol';
import { modelSeatKey, type ModelCompleted, type ModelConditions, type ModelDecision, type ModelSeat } from './arena-model';
import type { PolicyClient, PolicySource } from '../inference/policy-client';

type Baseline = Pick<SearchClient, 'search' | 'cancel' | 'dispose'>;
type ModelClient = Pick<PolicyClient, 'bestMove' | 'cancel' | 'dispose'>;
interface Operation { key: string | null; client: Pick<ModelClient, 'cancel'> | null }
const aborted = () => new DOMException('arena decision cancelled', 'AbortError');

/** Lazily owns at most the two selected model sessions. Baseline search stays independent. */
export class ArenaClient {
  private allowed = new Set<string>();
  private models = new Map<string, ModelClient>();
  private active: Operation | null = null;
  private disposed = false;
  constructor(private readonly baseline: Baseline = new SearchClient(),
    private readonly create: (source: PolicySource) => Promise<ModelClient> = async source => {
      const { PolicyClient } = await import('../inference/policy-client');
      return new PolicyClient(source);
    }) {}

  retainModels(seats: readonly ModelSeat[]): void {
    if (this.disposed) return;
    const allowed = new Set(seats.map(modelSeatKey));
    if (allowed.size > 2) throw new Error('only two AI model seats may be retained');
    if (this.active?.key && !allowed.has(this.active.key)) this.cancel();
    this.allowed = allowed;
    for (const [key, client] of this.models) if (!allowed.has(key)) { client.dispose(); this.models.delete(key); }
  }
  async search(input: SearchInput): ReturnType<SearchClient['search']> {
    if (this.disposed) throw new Error('arena client disposed');
    if (this.active) throw new Error('arena client busy');
    const operation: Operation = { key: null, client: this.baseline }; this.active = operation;
    try {
      const reply = await this.baseline.search(input);
      if (this.active !== operation || this.disposed) throw aborted();
      return reply;
    } finally { if (this.active === operation) this.active = null; }
  }
  async policy(input: ModelDecision): Promise<ModelCompleted> {
    if (this.disposed) throw new Error('arena client disposed');
    if (this.active) throw new Error('arena client busy');
    const seat = input.model, key = modelSeatKey(seat);
    if (!this.allowed.has(key)) throw new Error('model source is not selected');
    const root = { ...input.root };
    const conditions: ModelConditions = { sourceId: seat.sourceId, repo: seat.repo, revision: seat.revision, sourceCommit: seat.sourceCommit, license: seat.license, selection: { ...seat.selection } };
    const operation: Operation = { key, client: null }; this.active = operation;
    try {
      let client = this.models.get(key);
      if (!client) {
        const source: PolicySource = { selection: { ...seat.selection }, files: seat.files.map(file => ({ ...file })), fixtures: [...seat.fixtures], ...(seat.fp16WeightOnly ? { fp16WeightOnly: true } : {}) };
        client = await this.create(source);
        if (this.active !== operation || this.disposed || !this.allowed.has(key)) { client.dispose(); throw aborted(); }
        this.models.set(key, client);
      }
      operation.client = client;
      const reply = await client.bestMove(root);
      if (this.active !== operation || this.disposed) throw aborted();
      if (modelSeatKey({ sourceId: conditions.sourceId, selection: reply.result.selection }) !== key) throw new Error('model client returned a different format/backend identity');
      const choice = reply.result.choice;
      return { ...reply.result.root, kind: 'model-result', requestId: reply.requestId, model: conditions, validation: reply.validation,
        result: { bestMove: choice?.move ?? null, value: choice?.value ?? null, rawAction: choice?.rawAction ?? null, rawLegal: choice?.rawLegal ?? null },
        inferenceMs: reply.result.inferenceMs, roundTripMs: reply.roundTripMs };
    } catch (error) { if (this.active === operation) operation.client?.cancel(); throw error; }
    finally { if (this.active === operation) this.active = null; }
  }
  cancel(): void { const active = this.active; this.active = null; active?.client?.cancel(); }
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true; this.cancel(); this.baseline.dispose();
    for (const client of new Set(this.models.values())) client.dispose();
    this.models.clear(); this.allowed.clear();
  }
}
