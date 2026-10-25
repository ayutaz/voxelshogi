import { describe, expect, it } from 'vitest';
import { clickHand, clickSquare, NO_SELECTION, type Context } from '../src/game/interaction';
import { squareIndex } from '../src/game/model';

// A tiny fake position: only the engine's outputs matter here (board codes + legal move strings).
function ctx(legal: string[], pieces: Record<number, number>, side: 'b' | 'w' = 'b'): Context {
  const board = new Uint8Array(729);
  for (const [i, c] of Object.entries(pieces)) board[Number(i)] = c;
  return { legal, board, side };
}

const P = squareIndex(4, 3, 4); // black pawn (code 1) at 5四V
const T1 = squareIndex(4, 2, 4);
const ENEMY = squareIndex(0, 0, 0); // white pawn (code 15)

describe('clickSquare', () => {
  const c = ctx(['545535', '545535+', 'P*111'], { [P]: 1, [ENEMY]: 15 });

  it('selects an own piece that has legal moves and lists its targets', () => {
    const r = clickSquare(NO_SELECTION, P, c);
    expect(r.move).toBeNull();
    expect(r.selection.type).toBe('square');
    if (r.selection.type !== 'square') throw new Error();
    expect(r.selection.from).toBe(P);
    expect([...r.selection.targets.keys()]).toEqual([T1]);
  });

  it('asks for promotion when both options are legal', () => {
    const sel = clickSquare(NO_SELECTION, P, c).selection;
    const r = clickSquare(sel, T1, c);
    expect(r.move).toBeNull();
    expect(r.promotion).toEqual({ plain: '545535', promote: '545535+' });
    expect(r.selection).toBe(sel); // keeps the selection while the dialog is open
  });

  it('moves directly when only one option exists', () => {
    const c2 = ctx(['545535+'], { [P]: 1 });
    const sel = clickSquare(NO_SELECTION, P, c2).selection;
    const r = clickSquare(sel, T1, c2);
    expect(r.move).toBe('545535+');
    expect(r.selection).toEqual(NO_SELECTION);
  });

  it('ignores opponent pieces, empty squares and pieces without moves', () => {
    expect(clickSquare(NO_SELECTION, ENEMY, c)).toEqual({ selection: NO_SELECTION, move: null, promotion: null });
    expect(clickSquare(NO_SELECTION, squareIndex(5, 5, 5), c).selection).toEqual(NO_SELECTION);
    const stuck = ctx([], { [P]: 1 });
    expect(clickSquare(NO_SELECTION, P, stuck).selection).toEqual(NO_SELECTION);
  });

  it('re-selects another own piece or deselects on a non-target', () => {
    const Q = squareIndex(3, 3, 4);
    const c3 = ctx(['545535', '445435'], { [P]: 1, [Q]: 1 });
    const sel = clickSquare(NO_SELECTION, P, c3).selection;
    const r = clickSquare(sel, Q, c3);
    expect(r.selection.type === 'square' && r.selection.from).toBe(Q);
    expect(clickSquare(sel, squareIndex(8, 8, 8), c3).selection).toEqual(NO_SELECTION);
    expect(clickSquare(sel, P, c3).selection).toEqual(NO_SELECTION); // clicking the selected piece again
  });
});

describe('clickHand', () => {
  const c = ctx(['P*111', 'P*112', 'G*111'], {});

  it('selects a hand piece with drop targets and drops on click', () => {
    const r = clickHand(NO_SELECTION, 'P', c);
    expect(r.selection.type).toBe('hand');
    if (r.selection.type !== 'hand') throw new Error();
    expect(r.selection.targets.size).toBe(2);
    const d = clickSquare(r.selection, squareIndex(0, 0, 1), c);
    expect(d.move).toBe('P*112');
    expect(d.selection).toEqual(NO_SELECTION);
  });

  it('does nothing for kinds without drops and toggles off when clicked twice', () => {
    expect(clickHand(NO_SELECTION, 'R', c)).toEqual({ selection: NO_SELECTION, move: null, promotion: null });
    const sel = clickHand(NO_SELECTION, 'G', c).selection;
    expect(sel.type).toBe('hand');
    expect(clickHand(sel, 'G', c).selection).toEqual(NO_SELECTION);
  });
});
