import { describe, expect, it } from 'vitest';
import {
  coordsOf,
  decodePiece,
  displaySquare,
  dropTargets,
  handCounts,
  movesFrom,
  parseMove,
  sliceGrid,
  squareIndex,
  type Slice,
} from '../src/game/model';

describe('squares', () => {
  it('index = z*81 + y*9 + x and back', () => {
    expect(squareIndex(0, 0, 0)).toBe(0);
    expect(squareIndex(8, 8, 8)).toBe(728);
    expect(squareIndex(4, 8, 4)).toBe(4 * 81 + 8 * 9 + 4);
    for (let i = 0; i < 729; i++) {
      const { x, y, z } = coordsOf(i);
      expect(squareIndex(x, y, z)).toBe(i);
    }
    expect(() => squareIndex(9, 0, 0)).toThrow();
    expect(() => coordsOf(729)).toThrow();
  });

  it('displays 筋・段・層 like 5五V', () => {
    expect(displaySquare(squareIndex(4, 4, 4))).toBe('5五V');
    expect(displaySquare(squareIndex(0, 8, 8))).toBe('1九IX');
    expect(displaySquare(squareIndex(8, 0, 0))).toBe('9一I');
  });
});

describe('pieces', () => {
  it('decodes engine piece codes', () => {
    expect(decodePiece(0)).toBeNull();
    expect(decodePiece(1)).toEqual({ color: 'b', kind: 'P', promoted: false, label: '歩' });
    expect(decodePiece(8)).toEqual({ color: 'b', kind: 'K', promoted: false, label: '玉' });
    expect(decodePiece(14)).toEqual({ color: 'b', kind: 'R', promoted: true, label: '竜' });
    expect(decodePiece(15)).toEqual({ color: 'w', kind: 'P', promoted: false, label: '歩' });
    expect(decodePiece(22)).toEqual({ color: 'w', kind: 'K', promoted: false, label: '玉' });
    expect(decodePiece(27)).toEqual({ color: 'w', kind: 'B', promoted: true, label: '馬' });
    expect(() => decodePiece(29)).toThrow();
  });

  it('reads the 14-entry hands array', () => {
    const h = new Uint8Array([2, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 3]);
    expect(handCounts(h)).toEqual({
      b: { P: 2, L: 0, N: 0, S: 0, G: 1, B: 0, R: 0 },
      w: { P: 0, L: 0, N: 0, S: 0, G: 0, B: 0, R: 3 },
    });
    expect(() => handCounts(new Uint8Array(13))).toThrow();
  });
});

describe('moves', () => {
  it('parses board moves and drops', () => {
    expect(parseMove('577567')).toEqual({ from: squareIndex(4, 6, 6), to: squareIndex(4, 5, 6), promote: false, drop: null });
    expect(parseMove('533523+')).toEqual({ from: squareIndex(4, 2, 2), to: squareIndex(4, 1, 2), promote: true, drop: null });
    expect(parseMove('P*565')).toEqual({ from: null, to: squareIndex(4, 5, 4), promote: false, drop: 'P' });
    for (const bad of ['', '57756', '077567', 'K*555', 'P*55', '577567-']) {
      expect(() => parseMove(bad)).toThrow();
    }
  });

  it('groups legal moves from a square by target with promotion options', () => {
    const legal = ['533523', '533523+', '533524', 'P*111', '544534'];
    const m = movesFrom(legal, squareIndex(4, 2, 2));
    expect([...m.keys()].sort((a, b) => a - b)).toEqual([squareIndex(4, 1, 2), squareIndex(4, 1, 3)].sort((a, b) => a - b));
    expect(m.get(squareIndex(4, 1, 2))).toEqual({ plain: '533523', promote: '533523+' });
    expect(m.get(squareIndex(4, 1, 3))).toEqual({ plain: '533524', promote: null });
    // promotion-only target (e.g. pawn to last rank)
    const only = movesFrom(['522512+'], squareIndex(4, 1, 1));
    expect(only.get(squareIndex(4, 0, 1))).toEqual({ plain: null, promote: '522512+' });
  });

  it('lists drop targets for a hand piece kind', () => {
    const legal = ['P*111', 'P*112', 'G*111', '577567'];
    expect(dropTargets(legal, 'P')).toEqual(new Map([[squareIndex(0, 0, 0), 'P*111'], [squareIndex(0, 0, 1), 'P*112']]));
    expect(dropTargets(legal, 'R').size).toBe(0);
  });
});

describe('2D slices', () => {
  it('layer slice (fixed z) shows ranks top→bottom and files 9→1 left→right', () => {
    const s: Slice = { axis: 'z', index: 4 };
    const g = sliceGrid(s);
    expect(g.length).toBe(9);
    expect(g.every((row) => row.length === 9)).toBe(true);
    expect(g[0]![0]).toBe(squareIndex(8, 0, 4)); // 9一 top-left (Black's view)
    expect(g[8]![8]).toBe(squareIndex(0, 8, 4)); // 1九 bottom-right
  });

  it('rank slice (fixed y) shows layers IX→I top→bottom and files 9→1', () => {
    const g = sliceGrid({ axis: 'y', index: 6 });
    expect(g[0]![0]).toBe(squareIndex(8, 6, 8));
    expect(g[8]![0]).toBe(squareIndex(8, 6, 0));
    expect(g[8]![8]).toBe(squareIndex(0, 6, 0));
  });

  it('file slice (fixed x) shows layers IX→I top→bottom and ranks 一→九 left→right', () => {
    const g = sliceGrid({ axis: 'x', index: 0 });
    expect(g[0]![0]).toBe(squareIndex(0, 0, 8));
    expect(g[0]![8]).toBe(squareIndex(0, 8, 8));
    expect(g[8]![0]).toBe(squareIndex(0, 0, 0));
  });

  it('every slice covers 81 distinct squares sharing the fixed coordinate', () => {
    for (const axis of ['x', 'y', 'z'] as const) {
      for (let i = 0; i < 9; i++) {
        const cells = sliceGrid({ axis, index: i }).flat();
        expect(new Set(cells).size).toBe(81);
        expect(cells.every((c) => coordsOf(c)[axis] === i)).toBe(true);
      }
    }
  });
});

describe('formatMove', () => {
  it('formats board moves, promotions and drops in Japanese', async () => {
    const { formatMove } = await import('../src/game/model');
    expect(formatMove('577567')).toBe('5七VII→5六VII');
    expect(formatMove('533523+')).toBe('5三III→5二III成');
    expect(formatMove('P*565')).toBe('歩打 5六V');
    expect(formatMove('R*111')).toBe('飛打 1一I');
    expect(() => formatMove('bad')).toThrow();
  });
});
