// Observable wrapper around the WASM engine for React (useSyncExternalStore).
import { Game } from '../wasm/pkg/voxelshogi_wasm.js';
import type { Color } from './model';

/** Imports larger than this are rejected before they reach the engine. */
export const MAX_IMPORT_BYTES = 4 * 1024 * 1024;

export type ResultInfo =
  | { kind: 'win'; winner: Color; reason: 'Checkmate' | 'Resignation' | 'PerpetualCheck' }
  | { kind: 'draw'; reason: 'Repetition' | 'MaxPlies' };

export interface Snapshot {
  board: Uint8Array;
  hands: Uint8Array;
  side: Color;
  legal: string[];
  ply: number;
  moveCount: number;
  moves: string[];
  lastMove: string | null;
  result: ResultInfo | null;
  inCheck: Record<Color, boolean>;
  kingSquare: Record<Color, number>;
  hash: string;
}

export type ActionResult = { ok: true } | { ok: false; error: string };

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
    this.cached = {
      board,
      hands: g.hands(),
      side: g.sideToMove() === 'b' ? 'b' : 'w',
      legal: result ? [] : g.legalMoves(),
      ply: g.ply(),
      moveCount: g.moveCount(),
      moves: g.moveList(),
      lastMove: g.lastMove() ?? null,
      result,
      inCheck: { b: g.isInCheck(true), w: g.isInCheck(false) },
      kingSquare: { b: board.indexOf(BLACK_KING), w: board.indexOf(WHITE_KING) },
      hash: g.hash(),
    };
    return this.cached;
  };

  private changed(): void {
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
    return this.attempt(() => this.game.play(move));
  }

  undo(): void {
    if (this.game.undo()) this.changed();
  }

  redo(): void {
    if (this.game.redo()) this.changed();
  }

  goto(ply: number): ActionResult {
    return this.attempt(() => this.game.goto(ply));
  }

  resign(): void {
    this.game.resign();
    this.changed();
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
  }
}
