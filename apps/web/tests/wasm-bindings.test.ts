import { beforeAll, describe, expect, it } from 'vitest';
import { loadWasm } from './loadWasm';
import { Game, rulesetId } from '../src/wasm/pkg/voxelshogi_wasm.js';

beforeAll(() => loadWasm());

// Square index = z*81 + y*9 + x; piece code = 1 + kind + 14*color (kind: K=7).
const idx = (x: number, y: number, z: number) => z * 81 + y * 9 + x;

describe('wasm bindings', () => {
  it('exposes the ruleset id', () => {
    expect(rulesetId()).toBe('voxelshogi-standard-v1');
  });

  it('starts from the initial position', () => {
    const g = new Game();
    expect(g.sideToMove()).toBe('b');
    expect(g.ply()).toBe(0);
    const board = g.board();
    expect(board).toBeInstanceOf(Uint8Array);
    expect(board.length).toBe(729);
    expect(board.filter((c) => c !== 0).length).toBe(372);
    expect(board[idx(4, 8, 4)]).toBe(8); // black king
    expect(board[idx(4, 0, 4)]).toBe(22); // white king
    expect(Array.from(g.hands())).toEqual(new Array(14).fill(0));
    expect(g.legalMoves().length).toBe(424);
    expect(g.result()).toBeUndefined();
    expect(g.isInCheck(true)).toBe(false);
    g.free();
  });

  it('plays legal moves and rejects illegal ones without changing state', () => {
    const g = new Game();
    const before = g.hash();
    expect(() => g.play('555554')).toThrow();
    expect(() => g.play('nonsense')).toThrow();
    expect(g.hash()).toBe(before);
    g.play('577567');
    expect(g.sideToMove()).toBe('w');
    expect(g.ply()).toBe(1);
    expect(g.moveList()).toEqual(['577567']);
    expect(g.lastMove()).toBe('577567');
    expect(g.board()[idx(4, 5, 6)]).toBe(1); // black pawn moved
    expect(g.board()[idx(4, 6, 6)]).toBe(0);
    g.free();
  });

  it('supports undo, redo and goto', () => {
    const g = new Game();
    const h0 = g.hash();
    g.play('577567');
    const h1 = g.hash();
    g.play('533543');
    expect(g.undo()).toBe(true);
    expect(g.hash()).toBe(h1);
    expect(g.redo()).toBe(true);
    expect(g.ply()).toBe(2);
    g.goto(0);
    expect(g.hash()).toBe(h0);
    expect(g.moveCount()).toBe(2);
    expect(() => g.goto(3)).toThrow();
    g.free();
  });

  it('round-trips VSFEN and records, and validates imports', () => {
    const g = new Game();
    g.play('577567');
    g.play('533543');
    const v = Game.fromVsfen(g.vsfen());
    expect(v.hash()).toBe(g.hash());
    expect(() => Game.fromVsfen('not a position')).toThrow();
    const json = g.recordJson();
    expect(JSON.parse(json).ruleset_id).toBe('voxelshogi-standard-v1');
    const r = Game.fromRecordJson(json);
    expect(r.moveList()).toEqual(['577567', '533543']);
    expect(r.hash()).toBe(g.hash());
    expect(() => Game.fromRecordJson('{"ruleset_id":"x"}')).toThrow();
    for (const x of [g, v, r]) x.free();
  });

  it('reports resignation as a result', () => {
    const g = new Game();
    g.resign();
    const res = JSON.parse(g.result()!);
    expect(res).toEqual({ Win: { winner: 'White', reason: 'Resignation' } });
    expect(g.legalMoves()).toEqual([]);
    g.free();
  });
});
