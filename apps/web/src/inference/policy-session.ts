import type { Color } from '../game/model';
import type { BackendPort, OutputData, Profile, RuntimeInfo, SessionPort } from './backend';
import { compare, type Comparison } from './engine';
import type { LocalModel } from './local-model';
import { POLICY_ELEMENTS, fp16WeightOnly, type Backend, type Precision } from './manifest';
import { encodePosition, selectPolicyMove, type PolicyChoice } from './policy-contract';
import { TRAINED_NUMERIC_CONTRACT } from './numeric';

export interface PolicySelection { modelId: string; packageHash: string; precision: Precision; backend: Backend }
export interface PolicyRoot { revision: number; cursor: number; side: Color; hash: string; ruleset: string }
export interface PolicyPosition extends PolicyRoot { recordJson: string }
export interface PolicyGame {
  goto: (cursor: number) => void; ply: () => number; hash: () => string; sideToMove: () => string;
  isFinished: () => boolean; board: () => Uint8Array; hands: () => Uint8Array;
  legalMoves: () => string[]; free: () => void;
}
export interface PolicyDependencies {
  source: LocalModel;
  open: (backend: Backend, precision: Precision) => Promise<BackendPort>;
  game: (recordJson: string) => PolicyGame;
  now: () => number;
}
export interface PolicyValidation {
  fp16WeightOnly?: boolean;
  selection: PolicySelection;
  fixtures: { name: string; comparison: { policy: Comparison; value: Comparison } }[];
  information: RuntimeInfo; profile: Profile;
}
export interface PolicyReply { root: PolicyRoot; selection: PolicySelection; choice: PolicyChoice | null; finished: boolean; inferenceMs: number }

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid policy request');
  return value as Record<string, unknown>;
}
function integer(value: unknown, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= max;
}
export function parsePolicySelection(value: unknown): PolicySelection {
  const selected = record(value);
  if (Object.keys(selected).length !== 4 || typeof selected.modelId !== 'string' || !/^[A-Za-z0-9._-]{1,128}$/.test(selected.modelId) || typeof selected.packageHash !== 'string' || !/^[0-9a-f]{64}$/.test(selected.packageHash) ||
    !['fp32', 'fp16', 'int8'].includes(String(selected.precision)) || !['wasm', 'webgpu'].includes(String(selected.backend))) throw new Error('invalid policy model selection');
  return { ...selected } as unknown as PolicySelection;
}
export function parsePolicyPosition(value: unknown): PolicyPosition {
  const position = record(value);
  if (Object.keys(position).length !== 6 || !integer(position.revision) || !integer(position.cursor, 20000) || (position.side !== 'b' && position.side !== 'w') || typeof position.hash !== 'string' || !/^[0-9a-f]{16}$/.test(position.hash) ||
    position.ruleset !== 'voxelshogi-standard-v1' || typeof position.recordJson !== 'string' || position.recordJson.length < 1 || position.recordJson.length > 4 * 1024 * 1024 || new TextEncoder().encode(position.recordJson).length > 4 * 1024 * 1024) throw new Error('invalid policy position metadata');
  return { ...position } as unknown as PolicyPosition;
}
function floats(bytes: Uint8Array<ArrayBuffer>): Float32Array {
  if (bytes.byteOffset % 4 || bytes.byteLength % 4) throw new Error('unaligned reference tensor');
  return new Float32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4);
}

/** One model/precision/backend, one validated session. The client owns Worker replacement. */
export class PolicySession {
  private port: BackendPort | null = null;
  private session: SessionPort | null = null;
  private selection: PolicySelection | null = null;
  private ready = false;
  private busy = false;
  private disposed = false;
  constructor(private readonly deps: PolicyDependencies) {}

  private live() { if (this.disposed) throw new DOMException('policy session cancelled', 'AbortError'); }
  private placement(): Profile {
    const port = this.port!, selection = this.selection!, profile = port.profile();
    const expected = selection.backend === 'webgpu' ? 'WebGpuExecutionProvider' : 'CPUExecutionProvider';
    const providers = Object.entries(profile.providers);
    if (port.info.backend !== selection.backend || providers.length !== 1 || providers.some(([name, count]) => name !== expected || !Number.isSafeInteger(count) || count <= 0)) throw new Error('unverified policy backend placement');
    return profile;
  }
  private async close() {
    const session = this.session, port = this.port;
    this.session = null; this.port = null; this.ready = false;
    try { await session?.release(); } finally { await port?.dispose(); }
  }
  async initialize(value: unknown): Promise<PolicyValidation> {
    this.live();
    if (this.busy || this.selection) throw new Error('policy session already initialized or busy; create a new Worker');
    const selection = parsePolicySelection(value), source = this.deps.source;
    if (source.model.trained !== true || source.model.id !== selection.modelId || source.packageHash !== selection.packageHash) throw new Error('trained model identity differs from selection');
    if (source.model.numericContract !== TRAINED_NUMERIC_CONTRACT) throw new Error('unsupported trained numeric contract');
    const model = structuredClone(source.model), variant = model.variants.find(item => item.id === selection.precision);
    if (!variant) throw new Error('selected model precision is not available');
    this.selection = selection; this.busy = true;
    try {
      const bytes = await source.read(variant.model); this.live();
      const weightOnly = fp16WeightOnly(variant);
      this.port = await this.deps.open(selection.backend, weightOnly ? 'fp32' : selection.precision); this.live();
      if (weightOnly && this.port.info.computePrecision !== 'float32') throw new Error('FP16 weight-only requires FP32 compute');
      if (selection.backend === 'webgpu' && selection.precision === 'fp16' && !weightOnly && !this.port.info.features.includes('shader-f16')) throw new Error('shader-f16 is not available');
      this.port.resetProfile();
      this.session = await this.port.createSession(bytes, selection.precision); this.live();
      const fixtures: PolicyValidation['fixtures'] = [];
      for (const fixture of model.fixtures) {
        this.live();
        const game = this.deps.game(JSON.stringify(fixture.record));
        let features: Float32Array;
        try {
          if (game.sideToMove() !== fixture.side) throw new Error('fixture side differs from Rust state');
          features = encodePosition(game.board(), game.hands(), fixture.side);
        } finally { game.free(); }
        const reference = variant.references[fixture.name]!;
        const [input, policy, expectedValue] = await Promise.all([source.read(fixture.input), source.read(reference.policy), source.read(reference.value)]);
        this.live();
        const encoded = new Uint8Array(features.buffer);
        if (input.length !== encoded.length || input.some((byte, index) => byte !== encoded[index])) throw new Error('encoded model input differs from the fixed Python reference');
        const outputs = await this.session.run(features);
        try {
          this.live();
          const comparison = { policy: compare(floats(policy), outputs.policy, POLICY_ELEMENTS, selection.precision, model.numericContract, 'policy'), value: compare(floats(expectedValue), outputs.value, 1, selection.precision, model.numericContract, 'value') };
          if (Math.abs(outputs.value[0]!) > 1) throw new Error('Value exceeds tanh range');
          fixtures.push({ name: fixture.name, comparison });
        } finally { outputs.dispose(); }
      }
      if (fixtures.length === 0) throw new Error('policy session has no validated fixtures');
      // ORT 1.31.1 buffers native profile events until endProfiling/release.
      // End profiling once after the reference runs, retaining the exact session.
      await this.session.finishProfiling?.();
      this.live(); this.ready = true;
      return { selection: { ...selection }, fixtures, information: structuredClone(this.port.info), profile: this.placement(), ...(weightOnly ? { fp16WeightOnly: true } : {}) };
    } catch (error) { this.disposed = true; throw error; }
    finally { this.busy = false; if (this.disposed) await this.close(); }
  }

  async bestMove(value: unknown): Promise<PolicyReply> {
    this.live();
    if (this.busy) throw new Error('policy session busy');
    if (!this.ready || !this.selection || !this.session) throw new Error('policy session is not ready');
    const position = parsePolicyPosition(value), { recordJson, ...root } = position;
    this.busy = true;
    try {
      const game = this.deps.game(recordJson);
      let features: Float32Array, legal: string[];
      try {
        game.goto(root.cursor);
        if (game.ply() !== root.cursor || game.hash() !== root.hash || game.sideToMove() !== root.side) throw new Error('stale policy root differs from replayed Rust state');
        if (game.isFinished()) return { root, selection: { ...this.selection }, choice: null, finished: true, inferenceMs: 0 };
        legal = game.legalMoves();
        features = encodePosition(game.board(), game.hands(), root.side);
      } finally { game.free(); }
      this.live();
      const started = this.deps.now();
      let outputs: OutputData | undefined;
      try {
        outputs = await this.session.run(features);
        this.live();
        const choice = selectPolicyMove(outputs.policy, outputs.value, legal, root.side);
        this.placement();
        return { root, selection: { ...this.selection }, choice, finished: false, inferenceMs: this.deps.now() - started };
      } catch (error) { this.disposed = true; throw error; }
      finally { outputs?.dispose(); }
    } finally { this.busy = false; if (this.disposed) await this.close(); }
  }
  async dispose(): Promise<void> {
    this.disposed = true;
    if (!this.busy) await this.close();
  }
}
