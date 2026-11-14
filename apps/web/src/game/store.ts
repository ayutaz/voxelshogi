// Observable wrapper around the WASM engine for React (useSyncExternalStore).
import { Game, rulesetId } from '../wasm/pkg/voxelshogi_wasm.js';
import { recordOutcome } from './record-outcome';
import { parseMove, type Color } from './model';
import type { PresentationEvent, PresentationInput } from './presentation';

let storeIdentity = 0;

/** Imports larger than this are rejected before they reach the engine. */
export const MAX_IMPORT_BYTES = 4 * 1024 * 1024;

export type ResultInfo =
  | { kind: 'win'; winner: Color; reason: 'Checkmate' | 'Resignation' | 'PerpetualCheck' }
  | { kind: 'draw'; reason: 'Repetition' | 'MaxPlies' };

export interface Snapshot {
  revision: number;
  board: Uint8Array;
  hands: Uint8Array;
  side: Color;
  legal: string[];
  ply: number;
  moveCount: number;
  moves: string[];
  lastMove: string | null;
  result: ResultInfo | null;
  finished: boolean;
  terminalResult?: ResultInfo | null;
  terminalFinished?: boolean;
  inCheck: Record<Color, boolean>;
  kingSquare: Record<Color, number>;
  hash: string;
}

export type ActionResult = { ok: true } | { ok: false; error: string };
export interface SearchRoot { revision: number; cursor: number; ruleset: string; hash: string; side: Color }

const BLACK_KING = 8;
const WHITE_KING = 22;

function parseResult(json: string | undefined): ResultInfo | null {
  if (!json) return null;
  const r = JSON.parse(json) as { Win?: { winner: 'Black' | 'White'; reason: string }; Draw?: { reason: string } };
  if (r.Win) return { kind: 'win', winner: r.Win.winner === 'Black' ? 'b' : 'w', reason: r.Win.reason as never };
  if (r.Draw) return { kind: 'draw', reason: r.Draw.reason as never };
  throw new Error(`unknown result ${json}`);
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export class GameStore {
  private game: Game;
  private cached: Snapshot | null = null;
  private listeners = new Set<() => void>();
  private revision = 0;
  private identity = ++storeIdentity;
  private presentationSequence = 0;
  private presentationListeners = new Set<(event: PresentationEvent) => void>();

  subscribePresentation = (listener: (event: PresentationEvent) => void): (() => void) => {
    this.presentationListeners.add(listener);
    return () => this.presentationListeners.delete(listener);
  };

  private present(event: PresentationInput): void {
    const value = { ...event, id: `${this.identity}:${++this.presentationSequence}` };
    for (const listener of this.presentationListeners) {
      try { listener(value); } catch { /* Presentation never interrupts an accepted game operation. */ }
    }
  }

  private presentMove(before: Snapshot, move: string, kind: 'move' | 'forward'): void {
    const parsed = parseMove(move), after = this.snapshot();
    this.present({ kind, mover: before.side, capture: before.board[parsed.to] !== 0,
      promotion: parsed.promote, check: after.inCheck[after.side], result: after.result });
  }

  constructor(game: Game = new Game()) {
    this.game = game;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  snapshot = (): Snapshot => {
    if (this.cached) return this.cached;
    const g = this.game;
    const board = g.board();
    const result = parseResult(g.result());
    const recordJson = g.recordJson(), terminalResult = recordOutcome(recordJson);
    this.cached = {
      revision: this.revision,
      board,
      hands: g.hands(),
      side: g.sideToMove() === 'b' ? 'b' : 'w',
      legal: g.isFinished() ? [] : g.legalMoves(),
      ply: g.ply(),
      moveCount: g.moveCount(),
      moves: g.moveList(),
      lastMove: g.lastMove() ?? null,
      result,
      finished: g.isFinished(),
      terminalResult, terminalFinished: terminalResult !== null || JSON.parse(recordJson).termination != null,
      inCheck: { b: g.isInCheck(true), w: g.isInCheck(false) },
      kingSquare: { b: board.indexOf(BLACK_KING), w: board.indexOf(WHITE_KING) },
      hash: g.hash(),
    };
    return this.cached;
  };

  private changed(): void {
    this.revision += 1;
    this.cached = null;
    for (const l of this.listeners) l();
  }

  private attempt(f: () => void): ActionResult {
    try {
      f();
    } catch (e) {
      return { ok: false, error: errorMessage(e) };
    }
    this.changed();
    return { ok: true };
  }

  play(move: string): ActionResult {
    const before = this.snapshot();
    const result = this.attempt(() => this.game.play(move));
    if (result.ok) this.presentMove(before, move, 'move');
    return result;
  }

  searchState(): SearchRoot & { recordJson: string } {
    const s = this.snapshot();
    return { revision: s.revision, cursor: s.ply, hash: s.hash, side: s.side,
      ruleset: rulesetId(), recordJson: this.exportRecord() };
  }

  applyAiMove(root: SearchRoot, move: string): ActionResult {
    const s = this.snapshot();
    if (s.finished || root.revision !== s.revision || root.cursor !== s.ply || root.hash !== s.hash || root.side !== s.side || root.ruleset !== rulesetId()) {
      return { ok: false, error: 'stale AI response' };
    }
    return this.play(move);
  }

  undo(): void {
    if (this.game.undo()) { this.changed(); this.present({ kind: 'clear' }); }
  }

  redo(): void {
    if (this.game.redo()) { this.changed(); this.present({ kind: 'clear' }); }
  }

  goto(ply: number): ActionResult {
    const result = this.attempt(() => this.game.goto(ply));
    if (result.ok) this.present({ kind: 'clear' });
    return result;
  }

  stepForward(): ActionResult {
    const before = this.snapshot();
    if (before.ply >= before.moveCount) return { ok: true };
    const result = this.goto(before.ply + 1);
    if (result.ok) this.presentMove(before, before.moves[before.ply]!, 'forward');
    return result;
  }

  resign(): void {
    if (this.snapshot().finished) return;
    this.game.resign();
    this.changed();
    this.present({ kind: 'end', result: this.snapshot().result });
  }

  newGame(): void {
    this.replace(new Game());
  }

  exportRecord(): string {
    return this.game.recordJson();
  }

  importRecord(json: string): ActionResult {
    if (json.length > MAX_IMPORT_BYTES) return { ok: false, error: `record is larger than ${MAX_IMPORT_BYTES} bytes` };
    try {
      this.replace(Game.fromRecordJson(json));
      return { ok: true };
    } catch (e) {
      return { ok: false, error: errorMessage(e) };
    }
  }

  private replace(next: Game): void {
    this.game.free();
    this.game = next;
    this.changed();
    this.present({ kind: 'clear' });
  }
}
