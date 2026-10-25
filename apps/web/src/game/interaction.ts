// Click handling for board / hand selection. Pure functions: (selection, click) → result.
import { decodePiece, dropTargets, movesFrom, type Color, type HandKind, type TargetOptions } from './model';

export type Selection =
  | { type: 'none' }
  | { type: 'square'; from: number; targets: Map<number, TargetOptions> }
  | { type: 'hand'; kind: HandKind; targets: Map<number, string> };

/** What the engine currently says about the position. */
export interface Context {
  legal: readonly string[];
  board: Uint8Array;
  side: Color;
}

export interface ClickResult {
  selection: Selection;
  /** A complete move string to play now. */
  move: string | null;
  /** Both promoting and non-promoting moves are legal: ask the user. */
  promotion: { plain: string; promote: string } | null;
}

export const NO_SELECTION: Selection = { type: 'none' };

const none = (): ClickResult => ({ selection: NO_SELECTION, move: null, promotion: null });

function selectPiece(index: number, c: Context): ClickResult {
  const piece = decodePiece(c.board[index] ?? 0);
  if (!piece || piece.color !== c.side) return none();
  const targets = movesFrom(c.legal, index);
  if (targets.size === 0) return none();
  return { selection: { type: 'square', from: index, targets }, move: null, promotion: null };
}

export function clickSquare(sel: Selection, index: number, c: Context): ClickResult {
  if (sel.type === 'square') {
    const opt = sel.targets.get(index);
    if (opt) {
      if (opt.plain && opt.promote) return { selection: sel, move: null, promotion: { plain: opt.plain, promote: opt.promote } };
      return { selection: NO_SELECTION, move: opt.plain ?? opt.promote, promotion: null };
    }
    if (index === sel.from) return none();
  } else if (sel.type === 'hand') {
    const mv = sel.targets.get(index);
    if (mv) return { selection: NO_SELECTION, move: mv, promotion: null };
  }
  return selectPiece(index, c);
}

export function clickHand(sel: Selection, kind: HandKind, c: Context): ClickResult {
  if (sel.type === 'hand' && sel.kind === kind) return none();
  const targets = dropTargets(c.legal, kind);
  if (targets.size === 0) return none();
  return { selection: { type: 'hand', kind, targets }, move: null, promotion: null };
}
