import { formatMove, handCounts, HAND_KINDS, type Color, type HandKind } from '../game/model';
import type { Selection } from '../game/interaction';
import type { ResultInfo, Snapshot } from '../game/store';

const HAND_LABEL: Record<HandKind, string> = { P: '歩', L: '香', N: '桂', S: '銀', G: '金', B: '角', R: '飛' };
const SIDE = { b: '☗先手', w: '☖後手' } as const;

export function Hands({
  snap,
  color,
  selection,
  onHand,
}: {
  snap: Snapshot;
  color: Color;
  selection: Selection;
  onHand: (kind: HandKind) => void;
}) {
  const counts = handCounts(snap.hands)[color];
  const active = snap.side === color && !snap.result;
  const kinds = HAND_KINDS.filter((k) => counts[k] > 0);
  return (
    <div className={`hands hands-${color}`} data-testid={`hands-${color}`}>
      <span className="hands-title">{SIDE[color]} 持ち駒</span>
      {kinds.length === 0 ? <span className="muted">なし</span> : null}
      {kinds.map((k) => (
        <button
          key={k}
          type="button"
          className={selection.type === 'hand' && selection.kind === k && active ? 'hand selected' : 'hand'}
          disabled={!active}
          data-hand={k}
          onClick={() => onHand(k)}
        >
          {HAND_LABEL[k]}
          {counts[k] > 1 ? <small>×{counts[k]}</small> : null}
        </button>
      ))}
    </div>
  );
}

export function PromotionDialog({ onChoose, onCancel }: { onChoose: (promote: boolean) => void; onCancel: () => void }) {
  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-label="成りの選択">
      <div className="dialog">
        <p>成りますか？</p>
        <div className="row">
          <button type="button" className="primary" onClick={() => onChoose(true)}>
            成る
          </button>
          <button type="button" onClick={() => onChoose(false)}>
            成らない
          </button>
          <button type="button" className="ghost" onClick={onCancel}>
            キャンセル
          </button>
        </div>
      </div>
    </div>
  );
}

export function resultText(r: ResultInfo): string {
  if (r.kind === 'draw') return r.reason === 'Repetition' ? '千日手で引き分け' : '手数制限で引き分け';
  const why = { Checkmate: '詰み', Resignation: '投了', PerpetualCheck: '連続王手の千日手' }[r.reason];
  return `${SIDE[r.winner]}の勝ち（${why}）`;
}

export function MoveList({ snap, onGoto }: { snap: Snapshot; onGoto: (ply: number) => void }) {
  return (
    <ol className="move-list" data-testid="move-list">
      <li className={snap.ply === 0 ? 'current' : ''}>
        <button type="button" onClick={() => onGoto(0)}>
          開始局面
        </button>
      </li>
      {snap.moves.map((m, i) => (
        <li key={i} className={snap.ply === i + 1 ? 'current' : i + 1 > snap.ply ? 'future' : ''}>
          <button type="button" onClick={() => onGoto(i + 1)}>
            {i + 1}. {i % 2 === 0 ? '☗' : '☖'}
            {formatMove(m)}
          </button>
        </li>
      ))}
    </ol>
  );
}
