import { decodePiece, displaySquare, parseMove, sliceGrid, type Slice } from '../game/model';
import type { Selection } from '../game/interaction';
import type { BoardSnapshot } from '../game/boardSnapshot';

const KANJI = ['一', '二', '三', '四', '五', '六', '七', '八', '九'];
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];

interface Props {
  snap: BoardSnapshot;
  slice: Slice;
  selection: Selection;
  onSquare: (index: number) => void;
}

function axisLabels(slice: Slice): { rows: string[]; cols: string[]; title: string } {
  const files = Array.from({ length: 9 }, (_, c) => String(9 - c));
  const layersDown = Array.from({ length: 9 }, (_, r) => ROMAN[8 - r]!);
  if (slice.axis === 'z') return { rows: KANJI, cols: files, title: `${ROMAN[slice.index]}層` };
  if (slice.axis === 'y') return { rows: layersDown, cols: files, title: `${KANJI[slice.index]}段` };
  return { rows: layersDown, cols: KANJI, title: `${slice.index + 1}筋` };
}

/** One 9×9 cross-section of the cube; the primary way to make precise moves. */
export function Board2D({ snap, slice, selection, onSquare }: Props) {
  const grid = sliceGrid(slice);
  const { rows, cols, title } = axisLabels(slice);
  const targets = selection.type === 'none' ? new Set<number>() : new Set(selection.targets.keys());
  const last = snap.lastMove ? parseMove(snap.lastMove) : null;
  const checked = new Set<number>();
  if (snap.inCheck.b) checked.add(snap.kingSquare.b);
  if (snap.inCheck.w) checked.add(snap.kingSquare.w);

  return (
    <div className="board2d" aria-label={`2D断面 ${title}`}>
      <div className="board2d-title">{title}</div>
      <div className="board2d-grid">
        <div />
        {cols.map((c) => (
          <div key={c} className="axis-label">
            {c}
          </div>
        ))}
        {grid.map((row, r) => (
          <div key={r} className="board2d-row" style={{ display: 'contents' }}>
            <div className="axis-label">{rows[r]}</div>
            {row.map((index) => {
              const piece = decodePiece(snap.board[index] ?? 0);
              const classes = ['cell'];
              if (targets.has(index)) classes.push('target');
              if (selection.type === 'square' && selection.from === index) classes.push('selected');
              if (last && (last.to === index || last.from === index)) classes.push('last');
              if (checked.has(index)) classes.push('check');
              if (piece) classes.push(piece.color === 'b' ? 'black' : 'white');
              if (piece?.promoted) classes.push('promoted');
              return (
                <button
                  key={index}
                  type="button"
                  className={classes.join(' ')}
                  data-square={index}
                  title={displaySquare(index)}
                  onClick={() => onSquare(index)}
                >
                  {piece ? <span className="piece">{piece.label}</span> : null}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
