import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { Board2D } from './components/Board2D';
import { Hands, MoveList, PromotionDialog, resultText } from './components/Panels';
import type { LayerView } from './renderer/Board3D';
import { clickHand, clickSquare, NO_SELECTION, type ClickResult, type Selection } from './game/interaction';
import { coordsOf, type Color, type HandKind, type Slice } from './game/model';
import { GameStore, MAX_IMPORT_BYTES } from './game/store';
import { ArenaController, DEFAULT_AI_OPTIONS, type AiStatus } from './ai/arena-controller';

const Board3D = lazy(() => import('./renderer/Board3D').then((module) => ({ default: module.Board3D })));

type Controller = 'human' | 'ai';
type Mode = 'h-r' | 'r-h' | 'r-r';
const MODES: Record<Mode, { label: string; b: Controller; w: Controller }> = {
  'h-r': { label: '人間(先手) vs AI', b: 'human', w: 'ai' },
  'r-h': { label: 'AI vs 人間(後手)', b: 'ai', w: 'human' },
  'r-r': { label: 'AI vs AI 観戦', b: 'ai', w: 'ai' },
};
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];

export function App() {
  const store = useMemo(() => new GameStore(), []);
  const snap = useSyncExternalStore(store.subscribe, store.snapshot);
  const [selection, setSelection] = useState<Selection>(NO_SELECTION);
  const [promotion, setPromotion] = useState<ClickResult['promotion']>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('r-r');
  const [running, setRunning] = useState(false);
  const [difficulty, setDifficulty] = useState<Record<Color, 'easy' | 'normal'>>({ b: 'normal', w: 'normal' });
  const [budgetMs, setBudgetMs] = useState(1000);
  const [aiStatus, setAiStatus] = useState<AiStatus>({ phase: 'paused', error: null, last: null });
  const [delay, setDelay] = useState(400);
  const [view, setView] = useState<'3d' | '2d' | 'both'>('2d');
  const [slice, setSlice] = useState<Slice>({ axis: 'z', index: 4 });
  const [layers, setLayers] = useState<LayerView>({ mode: 'focus', z: 4, dim: 0.18 });
  const aiRef = useRef<ArenaController | null>(null);
  const importGeneration = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);

  const controller: Controller = MODES[mode][snap.side];
  const humanTurn = controller === 'human' && !snap.finished;
  const aiOptions = useMemo(() => ({ ...DEFAULT_AI_OPTIONS, mode, running, delayMs: delay,
    bDifficulty: difficulty.b, wDifficulty: difficulty.w,
    limits: { ...DEFAULT_AI_OPTIONS.limits, maxTimeMs: budgetMs } }), [mode, running, delay, difficulty, budgetMs]);

  useEffect(() => {
    const ai = new ArenaController(store);
    aiRef.current = ai;
    const unsubscribe = ai.subscribe(() => setAiStatus(ai.snapshot()));
    setAiStatus(ai.snapshot());
    return () => { importGeneration.current += 1; unsubscribe(); ai.dispose(); aiRef.current = null; };
  }, [store]);
  useEffect(() => { aiRef.current?.configure(aiOptions); }, [aiOptions]);

  const play = useCallback(
    (move: string) => {
      const r = store.play(move);
      setMessage(r.ok ? null : `指せません: ${r.error}`);
      setSelection(NO_SELECTION);
      setPromotion(null);
    },
    [store],
  );

  const pause = () => {
    importGeneration.current += 1;
    aiRef.current?.pause();
    aiRef.current?.resume();
    setRunning(false);
    setSelection(NO_SELECTION);
    setPromotion(null);
  };

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
    pause();
    store.newGame();
    setMode(m);
    setRunning(m !== 'r-r');
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
    pause();
    const generation = importGeneration.current;
    aiRef.current?.suspend();
    if (file.size > MAX_IMPORT_BYTES) {
      setMessage('棋譜ファイルが大きすぎます');
      aiRef.current?.resume();
      return;
    }
    setMessage('棋譜を読み込み中…');
    try {
      const text = await file.text();
      if (generation !== importGeneration.current) return;
      const r = store.importRecord(text);
      setMessage(r.ok ? '棋譜を読み込みました' : `読み込めません: ${r.error}`);
    } catch (error) {
      if (generation === importGeneration.current) setMessage(`読み込めません: ${String(error)}`);
    } finally {
      if (generation === importGeneration.current) aiRef.current?.resume();
    }
  };

  const status = snap.result
    ? resultText(snap.result)
    : snap.finished ? '対局中断' : `${snap.ply + 1}手目 ${snap.side === 'b' ? '☗先手' : '☖後手'}の番${snap.inCheck[snap.side] ? '（王手）' : ''}`;
  const phaseText = { paused: '一時停止中', waiting: '次の着手待ち', thinking: `${snap.side === 'b' ? '先手' : '後手'} ${difficulty[snap.side] === 'normal' ? 'Normal' : 'Easy'} 思考中…`,
    human: '人間の手番', history: '履歴表示中：1手指すと分岐します', finished: '対局終了', error: '探索エラー' }[aiStatus.phase];

  const sideHands = (c: Color) => <Hands snap={snap} color={c} selection={selection} onHand={onHand} />;

  return (
    <div className="app">
      <header>
        <h1>VoxelShogi Arena</h1>
        <span className="subtitle">9×9×9 三次元将棋</span>
        <a href="/?experiment=1">9王ルール比較室</a>
        <a href="/?models=1">モデル推論ラボ</a>
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
            <button type="button" onClick={() => { pause(); store.resign(); }} disabled={!humanTurn}>
              投了
            </button>
          </div>
          <div className="row">
            <button type="button" onClick={() => { pause(); store.undo(); }} disabled={snap.ply === 0} data-testid="undo">
              ◀ 1手戻る
            </button>
            <button type="button" onClick={() => { pause(); store.redo(); }} disabled={snap.ply === snap.moveCount} data-testid="redo">
              1手進む ▶
            </button>
          </div>
          {(['b', 'w'] as const).map((side) => <label key={side}>
            {side === 'b' ? '☗先手' : '☖後手'}のAI
            <select value={difficulty[side]} disabled={MODES[mode][side] === 'human'} data-testid={`difficulty-${side}`}
              onChange={(e) => { pause(); setDifficulty({ ...difficulty, [side]: e.target.value as 'easy' | 'normal' }); }}>
              <option value="easy">Easy（ランダム）</option><option value="normal">Normal（探索）</option>
            </select>
          </label>)}
          <label>Normalの思考上限
            <select value={budgetMs} data-testid="thinking-budget" onChange={(e) => { pause(); setBudgetMs(Number(e.target.value)); }}>
              <option value={100}>0.1秒</option><option value={1000}>約1秒</option><option value={3000}>約3秒</option>
            </select>
          </label>
          <p className="muted">Normalは最大6手先・50,000ノード。<a href="/build-info.json" target="_blank" rel="noreferrer">実装バージョン</a></p>
            <div className="watch">
              <div className="row">
                <button type="button" onClick={() => running ? pause() : setRunning(true)} data-testid="toggle-run" disabled={snap.finished}>
                  {running ? '一時停止' : '再開'}
                </button>
                <button
                  type="button"
                  data-testid="ai-step"
                  disabled={running || snap.finished || humanTurn || aiStatus.phase === 'thinking' || aiStatus.phase === 'waiting' || !!aiStatus.error}
                  onClick={() => aiRef.current?.step()}
                >
                  1手指す
                </button>
              </div>
              <label>
                着手間の待ち時間 {delay}ms（思考時間は別）
                <input data-testid="move-delay" type="range" min={50} max={2000} step={50} value={delay} onChange={(e) => setDelay(Number(e.target.value))} />
              </label>
              <p data-testid="ai-phase" role="status">{phaseText}</p>
              {aiStatus.phase === 'thinking' && <button type="button" data-testid="cancel-search" onClick={pause}>思考を中断</button>}
              {aiStatus.error && <div role="alert" data-testid="ai-error">{aiStatus.error}<button type="button" data-testid="ai-retry" onClick={() => aiRef.current?.retry()}>再試行</button></div>}
              {aiStatus.last?.kind === 'model-result' ? <p className="muted" data-testid="ai-analysis">
                直前の{aiStatus.last.side === 'b' ? '☗先手' : '☖後手'}AI：{aiStatus.last.model.selection.modelId}<br />
                {aiStatus.last.model.selection.precision.toUpperCase()}・{aiStatus.last.model.selection.backend === 'webgpu' ? 'WebGPU' : 'WASM'}<br />
                Value {aiStatus.last.result.value?.toFixed(3) ?? '未算出'}（直前のAIの視点）<br />
                推論{Math.round(aiStatus.last.inferenceMs)}ms・往復{Math.round(aiStatus.last.roundTripMs)}ms
              </p> : aiStatus.last && <p className="muted" data-testid="ai-analysis">
                直前の{aiStatus.last.side === 'b' ? '☗先手' : '☖後手'}AI：{aiStatus.last.difficulty === 'easy' ? 'Easy・ランダム着手（探索なし）' : `Normal・深さ${aiStatus.last.result.completedDepth}${aiStatus.last.result.completedDepth === 0 ? '・合法な代替手' : ''}`}<br />
                {aiStatus.last.result.score === null ? '評価は未算出' : Math.abs(aiStatus.last.result.score) === 1_000_000 ? `終局評価：${aiStatus.last.result.score > 0 ? '勝ち' : '負け'}` : `駒得 ${aiStatus.last.result.score >= 0 ? '+' : ''}${aiStatus.last.result.score}（歩=100、直前のAIの視点）`}<br />
                {aiStatus.last.result.nodes}ノード・往復{Math.round(aiStatus.last.roundTripMs)}ms・停止理由 {aiStatus.last.result.stopReason}
              </p>}
            </div>
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
              pause();
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
          {view !== '2d' ? <Suspense fallback={<p>3D盤面を読み込み中…</p>}><Board3D snap={snap} selection={selection} view={layers} onSquare={onSquare} /></Suspense> : null}
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
