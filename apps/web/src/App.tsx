import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { Board2D } from './components/Board2D';
import { Hands, MoveList, PromotionDialog, resultText } from './components/Panels';
import { Board3D, type LayerView } from './renderer/Board3D';
import { clickHand, clickSquare, NO_SELECTION, type ClickResult, type Selection } from './game/interaction';
import { coordsOf, type Color, type HandKind, type Slice } from './game/model';
import { GameStore, MAX_IMPORT_BYTES } from './game/store';
import { createRng, pickRandomMove } from './ai/random';

type Controller = 'human' | 'random';
type Mode = 'hvh' | 'h-r' | 'r-h' | 'r-r';
const MODES: Record<Mode, { label: string; b: Controller; w: Controller }> = {
  hvh: { label: '人間 vs 人間', b: 'human', w: 'human' },
  'h-r': { label: '人間(先手) vs ランダムAI', b: 'human', w: 'random' },
  'r-h': { label: 'ランダムAI vs 人間(後手)', b: 'random', w: 'human' },
  'r-r': { label: 'AI vs AI 観戦', b: 'random', w: 'random' },
};
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];

export function App() {
  const store = useMemo(() => new GameStore(), []);
  const snap = useSyncExternalStore(store.subscribe, store.snapshot);
  const [selection, setSelection] = useState<Selection>(NO_SELECTION);
  const [promotion, setPromotion] = useState<ClickResult['promotion']>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('hvh');
  const [running, setRunning] = useState(true);
  const [delay, setDelay] = useState(400);
  const [view, setView] = useState<'3d' | '2d' | 'both'>('both');
  const [slice, setSlice] = useState<Slice>({ axis: 'z', index: 4 });
  const [layers, setLayers] = useState<LayerView>({ mode: 'focus', z: 4, dim: 0.18 });
  const rng = useRef(createRng(Date.now() >>> 0));
  const fileInput = useRef<HTMLInputElement>(null);

  const controller: Controller = MODES[mode][snap.side];
  const humanTurn = controller === 'human' && !snap.result;

  const play = useCallback(
    (move: string) => {
      const r = store.play(move);
      setMessage(r.ok ? null : `指せません: ${r.error}`);
      setSelection(NO_SELECTION);
      setPromotion(null);
    },
    [store],
  );

  // AI turns
  useEffect(() => {
    if (snap.result || controller === 'human' || snap.ply !== snap.moveCount) return;
    if (mode === 'r-r' && !running) return;
    const t = setTimeout(() => {
      const mv = pickRandomMove(snap.legal, rng.current);
      if (mv) play(mv);
    }, delay);
    return () => clearTimeout(t);
  }, [snap, controller, mode, running, delay, play]);

  const ctx = { legal: snap.legal, board: snap.board, side: snap.side };
  const apply = (r: ClickResult) => {
    setSelection(r.selection);
    if (r.promotion) setPromotion(r.promotion);
    if (r.move) play(r.move);
  };
  const onSquare = (index: number) => {
    if (!humanTurn) return;
    apply(clickSquare(selection, index, ctx));
    // follow the clicked square in the 2D view when it is on another layer
    const z = coordsOf(index).z;
    if (slice.axis === 'z' && z !== slice.index && selection.type === 'none') setSlice({ axis: 'z', index: z });
  };
  const onHand = (kind: HandKind) => humanTurn && apply(clickHand(selection, kind, ctx));

  const reset = (m: Mode = mode) => {
    store.newGame();
    setMode(m);
    setSelection(NO_SELECTION);
    setPromotion(null);
    setMessage(null);
  };

  const exportRecord = () => {
    const blob = new Blob([store.exportRecord()], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `voxelshogi-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const importRecord = async (file: File) => {
    if (file.size > MAX_IMPORT_BYTES) {
      setMessage('棋譜ファイルが大きすぎます');
      return;
    }
    const r = store.importRecord(await file.text());
    setMessage(r.ok ? '棋譜を読み込みました' : `読み込めません: ${r.error}`);
    setSelection(NO_SELECTION);
    if (r.ok) setMode('hvh');
  };

  const status = snap.result
    ? resultText(snap.result)
    : `${snap.ply + 1}手目 ${snap.side === 'b' ? '☗先手' : '☖後手'}の番${snap.inCheck[snap.side] ? '（王手）' : ''}`;

  const sideHands = (c: Color) => <Hands snap={snap} color={c} selection={selection} onHand={onHand} />;

  return (
    <div className="app">
      <header>
        <h1>VoxelShogi Arena</h1>
        <span className="subtitle">9×9×9 三次元将棋</span>
        <span className="status" data-testid="status" role="status">
          {status}
        </span>
      </header>

      <aside className="panel left">
        <section>
          <h2>対局</h2>
          <label>
            モード
            <select value={mode} onChange={(e) => reset(e.target.value as Mode)} data-testid="mode">
              {Object.entries(MODES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
          <div className="row">
            <button type="button" onClick={() => reset()}>
              新規対局
            </button>
            <button type="button" onClick={() => store.resign()} disabled={!humanTurn}>
              投了
            </button>
          </div>
          <div className="row">
            <button type="button" onClick={() => store.undo()} disabled={snap.ply === 0} data-testid="undo">
              ◀ 1手戻る
            </button>
            <button type="button" onClick={() => store.redo()} disabled={snap.ply === snap.moveCount} data-testid="redo">
              1手進む ▶
            </button>
          </div>
          {mode === 'r-r' ? (
            <div className="watch">
              <div className="row">
                <button type="button" onClick={() => setRunning(!running)} data-testid="toggle-run">
                  {running ? '一時停止' : '再開'}
                </button>
                <button
                  type="button"
                  disabled={running || !!snap.result}
                  onClick={() => {
                    const mv = pickRandomMove(snap.legal, rng.current);
                    if (mv) play(mv);
                  }}
                >
                  1手指す
                </button>
              </div>
              <label>
                速度 {delay}ms/手
                <input type="range" min={50} max={2000} step={50} value={delay} onChange={(e) => setDelay(Number(e.target.value))} />
              </label>
              <p className="muted">☗ ランダムAI vs ☖ ランダムAI（ブラウザ内でリアルタイムに推論）</p>
            </div>
          ) : null}
        </section>
        <section>
          <h2>棋譜</h2>
          <div className="row">
            <button type="button" onClick={exportRecord}>
              保存
            </button>
            <button type="button" onClick={() => fileInput.current?.click()}>
              読み込み
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              hidden
              data-testid="import"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importRecord(f);
                e.target.value = '';
              }}
            />
          </div>
          <MoveList
            snap={snap}
            onGoto={(p) => {
              store.goto(p);
              setSelection(NO_SELECTION);
            }}
          />
        </section>
      </aside>

      <main>
        {message ? (
          <div className="message" role="alert">
            {message}
          </div>
        ) : null}
        {sideHands('w')}
        <div className={`views views-${view}`}>
          {view !== '2d' ? <Board3D snap={snap} selection={selection} view={layers} onSquare={onSquare} /> : null}
          {view !== '3d' ? <Board2D snap={snap} slice={slice} selection={selection} onSquare={onSquare} /> : null}
        </div>
        {sideHands('b')}
      </main>

      <aside className="panel right">
        <section>
          <h2>表示</h2>
          <div className="row" role="radiogroup" aria-label="表示モード">
            {(['both', '3d', '2d'] as const).map((v) => (
              <button key={v} type="button" className={view === v ? 'primary' : ''} onClick={() => setView(v)}>
                {{ both: '3D+2D', '3d': '3D', '2d': '2D' }[v]}
              </button>
            ))}
          </div>
        </section>
        <section>
          <h2>3D 層の表示</h2>
          <label className="check">
            <input
              type="checkbox"
              checked={layers.mode === 'all'}
              onChange={(e) => setLayers({ ...layers, mode: e.target.checked ? 'all' : 'focus' })}
            />
            全層を同じ濃さで表示
          </label>
          <label>
            注目する層: {ROMAN[layers.z]}
            <input
              type="range"
              min={0}
              max={8}
              value={layers.z}
              onChange={(e) => {
                const z = Number(e.target.value);
                setLayers({ ...layers, z });
                if (slice.axis === 'z') setSlice({ axis: 'z', index: z });
              }}
            />
          </label>
          <label>
            他の層の不透明度: {Math.round(layers.dim * 100)}%
            <input
              type="range"
              min={0}
              max={0.6}
              step={0.02}
              value={layers.dim}
              disabled={layers.mode === 'all'}
              onChange={(e) => setLayers({ ...layers, dim: Number(e.target.value) })}
            />
          </label>
        </section>
        <section>
          <h2>2D 断面</h2>
          <div className="row">
            {(['z', 'y', 'x'] as const).map((a) => (
              <button
                key={a}
                type="button"
                className={slice.axis === a ? 'primary' : ''}
                onClick={() => setSlice({ axis: a, index: slice.index })}
              >
                {{ z: '層', y: '段', x: '筋' }[a]}で切る
              </button>
            ))}
          </div>
          <label>
            位置: {slice.index + 1}
            <input
              type="range"
              min={0}
              max={8}
              value={slice.index}
              data-testid="slice-index"
              onChange={(e) => {
                const index = Number(e.target.value);
                setSlice({ ...slice, index });
                if (slice.axis === 'z') setLayers({ ...layers, z: index });
              }}
            />
          </label>
        </section>
        <section className="help">
          <h2>操作</h2>
          <p>駒をクリックすると移動先が緑で表示されます。3D はドラッグで回転、ホイールで拡大。精密な操作は 2D 断面がおすすめです。</p>
          <p className="muted">
            ルール: <a href="https://shogitter.com/rule/三次元将棋">将棋ったー「三次元将棋」</a>準拠（ruleset voxelshogi-standard-v1）
          </p>
        </section>
      </aside>

      {promotion ? (
        <PromotionDialog
          onChoose={(p) => play(p ? promotion.promote : promotion.plain)}
          onCancel={() => {
            setPromotion(null);
            setSelection(NO_SELECTION);
          }}
        />
      ) : null}
    </div>
  );
}
