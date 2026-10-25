// Pure helpers for the UI (no DOM). The rules themselves live in the Rust engine;
// these only decode its outputs (piece codes, move strings) and lay out views.

export type Color = 'b' | 'w';
export type Kind = 'P' | 'L' | 'N' | 'S' | 'G' | 'B' | 'R' | 'K';
export type HandKind = Exclude<Kind, 'K'>;
export interface PieceInfo {
  color: Color;
  kind: Kind;
  promoted: boolean;
  label: string;
}
export interface ParsedMove {
  from: number | null;
  to: number;
  promote: boolean;
  drop: HandKind | null;
}
/** Move strings reaching one target square: without and with promotion. */
export interface TargetOptions {
  plain: string | null;
  promote: string | null;
}
/** A 9×9 cross-section of the cube with one coordinate fixed. */
export type Slice = { axis: 'x' | 'y' | 'z'; index: number };

export const HAND_KINDS: readonly HandKind[] = ['P', 'L', 'N', 'S', 'G', 'B', 'R'];
// Engine kind order: P L N S G B R K +P +L +N +S +B +R
const KIND_ORDER: readonly Kind[] = ['P', 'L', 'N', 'S', 'G', 'B', 'R', 'K', 'P', 'L', 'N', 'S', 'B', 'R'];
const LABELS = ['歩', '香', '桂', '銀', '金', '角', '飛', '玉', 'と', '杏', '圭', '全', '馬', '竜'];
const KANJI = ['一', '二', '三', '四', '五', '六', '七', '八', '九'];
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];

const inRange = (v: number) => Number.isInteger(v) && v >= 0 && v < 9;

export function squareIndex(x: number, y: number, z: number): number {
  if (!inRange(x) || !inRange(y) || !inRange(z)) throw new RangeError(`square out of range: ${x},${y},${z}`);
  return z * 81 + y * 9 + x;
}

export function coordsOf(i: number): { x: number; y: number; z: number } {
  if (!Number.isInteger(i) || i < 0 || i >= 729) throw new RangeError(`square index out of range: ${i}`);
  return { x: i % 9, y: Math.floor(i / 9) % 9, z: Math.floor(i / 81) };
}

/** 筋・段・層, e.g. `5五V`. */
export function displaySquare(i: number): string {
  const { x, y, z } = coordsOf(i);
  return `${x + 1}${KANJI[y]}${ROMAN[z]}`;
}

export function decodePiece(code: number): PieceInfo | null {
  if (code === 0) return null;
  if (!Number.isInteger(code) || code < 1 || code > 28) throw new RangeError(`bad piece code ${code}`);
  const c = code - 1;
  const k = c % 14;
  return { color: c >= 14 ? 'w' : 'b', kind: KIND_ORDER[k]!, promoted: k >= 8, label: LABELS[k]! };
}

export function handCounts(h: Uint8Array): Record<Color, Record<HandKind, number>> {
  if (h.length !== 14) throw new RangeError(`hands must have 14 entries, got ${h.length}`);
  const side = (offset: number) =>
    Object.fromEntries(HAND_KINDS.map((k, i) => [k, h[offset + i]!])) as Record<HandKind, number>;
  return { b: side(0), w: side(7) };
}

function parseSquare(s: string): number {
  if (!/^[1-9]{3}$/.test(s)) throw new SyntaxError(`bad square ${JSON.stringify(s)}`);
  return squareIndex(Number(s[0]) - 1, Number(s[1]) - 1, Number(s[2]) - 1);
}

export function parseMove(s: string): ParsedMove {
  const drop = /^([PLNSGBR])\*([1-9]{3})$/.exec(s);
  if (drop) return { from: null, to: parseSquare(drop[2]!), promote: false, drop: drop[1] as HandKind };
  const normal = /^([1-9]{3})([1-9]{3})(\+?)$/.exec(s);
  if (!normal) throw new SyntaxError(`bad move ${JSON.stringify(s)}`);
  return { from: parseSquare(normal[1]!), to: parseSquare(normal[2]!), promote: normal[3] === '+', drop: null };
}

export function movesFrom(legal: readonly string[], from: number): Map<number, TargetOptions> {
  const out = new Map<number, TargetOptions>();
  for (const s of legal) {
    const m = parseMove(s);
    if (m.from !== from) continue;
    const opt = out.get(m.to) ?? { plain: null, promote: null };
    if (m.promote) opt.promote = s;
    else opt.plain = s;
    out.set(m.to, opt);
  }
  return out;
}

export function dropTargets(legal: readonly string[], kind: HandKind): Map<number, string> {
  const out = new Map<number, string>();
  for (const s of legal) {
    const m = parseMove(s);
    if (m.drop === kind) out.set(m.to, s);
  }
  return out;
}

/**
 * Rows top→bottom, columns left→right, as seen by Black:
 * - axis z (one layer): ranks 一→九 by files 9→1 (an ordinary shogi diagram)
 * - axis y (one rank): layers IX→I by files 9→1
 * - axis x (one file): layers IX→I by ranks 一→九
 */
export function sliceGrid(s: Slice): number[][] {
  if (!inRange(s.index)) throw new RangeError(`slice index out of range: ${s.index}`);
  const rows: number[][] = [];
  for (let r = 0; r < 9; r++) {
    const row: number[] = [];
    for (let c = 0; c < 9; c++) {
      if (s.axis === 'z') row.push(squareIndex(8 - c, r, s.index));
      else if (s.axis === 'y') row.push(squareIndex(8 - c, s.index, 8 - r));
      else row.push(squareIndex(s.index, c, 8 - r));
    }
    rows.push(row);
  }
  return rows;
}

const HAND_LABELS: Record<HandKind, string> = { P: '歩', L: '香', N: '桂', S: '銀', G: '金', B: '角', R: '飛' };

/** Human-readable move: `5七VII→5六VII`, `…成`, or `歩打 5六V`. */
export function formatMove(s: string): string {
  const m = parseMove(s);
  if (m.drop) return `${HAND_LABELS[m.drop]}打 ${displaySquare(m.to)}`;
  return `${displaySquare(m.from!)}→${displaySquare(m.to)}${m.promote ? '成' : ''}`;
}
