import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { Board2D } from './components/Board2D';
import { Hands, MoveList, PromotionDialog, resultText } from './components/Panels';
import type { LayerView } from './renderer/Board3D';
import { clickHand, clickSquare, NO_SELECTION, type ClickResult, type Selection } from './game/interaction';
import { coordsOf, formatMove, parseMove, type Color, type HandKind, type Slice } from './game/model';
import { followView, layerTargets } from './game/spectator';
import { GameStore, MAX_IMPORT_BYTES } from './game/store';
import { ArenaController, DEFAULT_AI_OPTIONS, type AiStatus, type ArenaDifficulty } from './ai/arena-controller';
import { addModel, chooseModel, modelSeat, removeModel, type LoadedModel, type ModelChoice, type ModelLibrary } from './ai/model-library';
import { arenaConditions } from './ai/arena-record';
import { ARENA_LINKS } from './navigation';
import { fp16WeightOnly } from './inference/manifest';
import { BoardFrame } from './components/BoardFrame';
import { Sheet } from './components/Sheet';
import { AutomaticCollection } from './collection/automatic-client';
import { collectionAgents } from './collection/agents';

const Board3D = lazy(() => import('./renderer/Board3D').then((module) => ({ default: module.Board3D })));
const ModelLibraryPanel = lazy(() => import('./inference/ModelLibraryPanel'));

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
  const [resultDismissed,setResultDismissed] = useState(false);
  const [mode, setMode] = useState<Mode>('r-r');
  const [running, setRunning] = useState(false);
  const [difficulty, setDifficulty] = useState<Record<Color, ArenaDifficulty>>({ b: 'normal', w: 'normal' });
  const [library, setLibrary] = useState<ModelLibrary>({ entries: [], choices: {} });
  const [showModels, setShowModels] = useState(false);
  const ownedRecord = useRef(true);
  const collection = useRef<AutomaticCollection | null>(null);
  const sourceSequence = useRef(0);
  const [budgetMs, setBudgetMs] = useState(1000);
  const [aiStatus, setAiStatus] = useState<AiStatus>({ phase: 'paused', error: null, last: null });
  const [delay, setDelay] = useState(400);
  const [view, setView] = useState<'3d' | '2d' | 'both'>('both');
  const [rawSlice, setSlice] = useState<Slice>({ axis: 'z', index: 4 });
  const [rawLayers, setLayers] = useState<LayerView>({ mode: 'all', z: 4, dim: 0.4 });
  const [follow, setFollow] = useState(true);
  const [trail, setTrail] = useState(true);
  const [sheet, setSheet] = useState<'match' | 'settings' | 'record' | 'display' | 'models' | 'research' | null>(null);
  const [matchKind, setMatchKind] = useState<'watch' | 'human'>('human');
  const [draftMode, setDraftMode] = useState<Mode>('h-r');
  const [draftOpponent, setDraftOpponent] = useState<ArenaDifficulty>('normal');
  const [draftPrecision, setDraftPrecision] = useState<ModelChoice['precision']>('int8');
  const [publicModelState, setPublicModelState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [publicAttempt, setPublicAttempt] = useState(0);
  const needsPublicModel = library.entries.length === 0 && ((sheet === 'match' && draftOpponent === 'model') || sheet === 'models' || sheet === 'settings');
  useEffect(() => {
    if (!needsPublicModel) return;
    const abort = new AbortController();
    setPublicModelState('loading');
    void import('./inference/public-model').then(module => module.preparePublicModel(abort.signal)).then(packet => {
      if (abort.signal.aborted) return;
      const entry = { ...packet, sourceId: `public-${++sourceSequence.current}` };
      setLibrary(previous => previous.entries.length ? previous : addModel(previous, entry));
      setPublicModelState('idle');
    }).catch(() => { if (!abort.signal.aborted) setPublicModelState('error'); });
    return () => abort.abort();
  }, [needsPublicModel, publicAttempt]);
  const { slice, layers } = followView(snap.lastMove, follow && selection.type === 'none', rawSlice, rawLayers);
  const targetCounts = layerTargets(selection.type === 'none' ? [] : selection.targets.keys());
  const manualView = () => { setSlice(slice); setLayers(layers); setFollow(false); };
  const aiRef = useRef<ArenaController | null>(null);
  const importGeneration = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);

  const controller: Controller = MODES[mode][snap.side];
  const humanTurn = controller === 'human' && !snap.finished && snap.ply === snap.moveCount;
  const stepBusy = aiStatus.phase === 'thinking' || aiStatus.phase === 'waiting';
  const aiOptions = useMemo(() => ({ ...DEFAULT_AI_OPTIONS, mode, running, delayMs: delay,
    bDifficulty: difficulty.b, wDifficulty: difficulty.w, bModel: modelSeat(library, 'b'), wModel: modelSeat(library, 'w'),
    limits: { ...DEFAULT_AI_OPTIONS.limits, maxTimeMs: budgetMs } }), [mode, running, delay, difficulty, budgetMs, library]);
  const currentOptions = useRef(aiOptions);
  useEffect(() => { currentOptions.current = aiOptions; }, [aiOptions]);
  useEffect(() => {
    const instance = new AutomaticCollection(); collection.current = instance;
    const capture = () => {
      try {
        if (!ownedRecord.current) throw new Error('imported record');
        const options = currentOptions.current;
        instance.observe(store.exportRecord(), { mode: options.mode, selectedAgents: collectionAgents(options) });
      } catch { /* Saving never interrupts the game. */ }
    };
    const unsubscribe = store.subscribe(capture); capture();
    const flush = () => instance.flush();
    const visibility = () => { if (document.visibilityState === 'hidden') flush(); };
    window.addEventListener('pagehide', flush); document.addEventListener('visibilitychange', visibility);
    return () => { unsubscribe(); window.removeEventListener('pagehide', flush); document.removeEventListener('visibilitychange', visibility); instance.dispose(); collection.current = null; };
  }, [store]);

  useEffect(() => {
    const ai = new ArenaController(store);
    aiRef.current = ai;
    const unsubscribe = ai.subscribe(() => setAiStatus(ai.snapshot()));
    setAiStatus(ai.snapshot());
    return () => { importGeneration.current += 1; unsubscribe(); ai.dispose(); aiRef.current = null; };
  }, [store]);
  // Imperative pause during replacement must be reconciled even if settings stay equal.
  useEffect(() => { aiRef.current?.configure(aiOptions); }, [aiOptions, snap.revision]);

  const play = useCallback(
    (move: string) => {
      const r = store.play(move);
      setMessage(r.ok ? null : `指せません: ${r.error}`);
      setSelection(NO_SELECTION);
      setPromotion(null);
      if (r.ok && mode !== 'r-r') setRunning(true);
    },
    [store,mode],
  );

  const pause = () => {
    importGeneration.current += 1;
    aiRef.current?.pause();
    aiRef.current?.resume();
    setRunning(false);
    setSelection(NO_SELECTION);
    setPromotion(null);
    collection.current?.flush();
  };
  const loadedModel = (packet: Omit<LoadedModel, 'sourceId'>) => {
    const next = addModel(library, { ...packet, sourceId: `local-${++sourceSequence.current}` });
    if (snap.moveCount > 0 && (difficulty.b === 'model' || difficulty.w === 'model') && !reset()) return;
    pause(); setLibrary(next);
  };
  const choose = (side: Color, choice: ModelChoice) => {
    const next = chooseModel(library, side, choice);
    if (snap.moveCount > 0 && difficulty[side] === 'model' && !reset()) return;
    pause(); setLibrary(next);
  };
  const selectDifficulty = (side: Color, value: ArenaDifficulty) => {
    if (value === difficulty[side]) return;
    if (snap.moveCount > 0 && !reset()) return;
    pause();
    if (value === 'model' && !library.choices[side]) {
      const first = library.entries[0];
      if (!first) return;
      setLibrary(chooseModel(library, side, { sourceId: first.sourceId, precision: first.model.variants[0]!.precision, backend: 'wasm' }));
    }
    setDifficulty({ ...difficulty, [side]: value });
  };

  const ctx = { legal: snap.legal, board: snap.board, side: snap.side };
  const apply = (r: ClickResult) => {
    setSelection(r.selection);
    if (r.promotion) setPromotion(r.promotion);
    if (r.move) play(r.move);
  };
  const onSquare = (index: number) => {
    if (!humanTurn) return;
    setSlice(slice); setLayers(layers);
    apply(clickSquare(selection, index, ctx));
    // follow the clicked square in the 2D view when it is on another layer
    const z = coordsOf(index).z;
    if (slice.axis === 'z' && z !== slice.index && selection.type === 'none') setSlice({ axis: 'z', index: z });
  };
  const onHand = (kind: HandKind) => { if (humanTurn) { setSlice(slice); setLayers(layers); apply(clickHand(selection, kind, ctx)); } };

  const allowReplacement = () => snap.moveCount === 0 || window.confirm('現在の対局を置き換えます。必要なら先に棋譜を保存してください。続けますか？');
  const reset = (m: Mode = mode) => {
    if (!allowReplacement()) return false;
    pause();
    setResultDismissed(false);
    setFollow(true); setSlice({ axis: 'z', index: 4 }); setLayers({ ...rawLayers, z: 4 });
    if (m !== 'r-r') setView('2d');
    aiRef.current?.journal.clear();
    collection.current?.begin(true);
    ownedRecord.current = true;
    store.newGame();
    setMode(m);
    setRunning(m !== 'r-r');
    setSelection(NO_SELECTION);
    setPromotion(null);
    setMessage(null);
    return true;
  };

  const downloadRecord = (text: string, suffix = '') => {
    const blob = new Blob([text], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `voxelshogi${suffix}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const exportRecord = () => downloadRecord(store.exportRecord());
  const exportConditions = async () => {
    pause();
    // Freeze game and observations before the asynchronous build-info request.
    const recordJson = store.exportRecord(), current = store.snapshot();
    const selectedAgents = arenaConditions(aiOptions);
    const automaticGameId = ownedRecord.current ? collection.current?.gameId : null;
    const snapshot = { schema: 1, kind: 'voxelshogi-arena-record', record: JSON.parse(recordJson) as unknown,
      viewCursor: current.ply, positionHash: current.hash, observationsThroughCursor: aiRef.current?.journal.snapshot(recordJson, current.ply) ?? [] };
    try {
      const response = await fetch('/build-info.json', { cache: 'no-store', credentials: 'omit', redirect: 'error' });
      if (!response.ok) throw new Error('実装バージョンを取得できません');
      const build = await response.json() as { commit?: unknown };
      if (typeof build.commit !== 'string' || !/^[0-9a-f]{40}$/.test(build.commit)) throw new Error('実装バージョンが不正です');
      downloadRecord(JSON.stringify({ ...snapshot, selectedAgents, applicationCommit: build.commit,
        automaticGameId }, null, 2), '-with-ai');
    } catch (error) { setMessage(`保存できません: ${String(error)}`); }
  };
  const importRecord = async (file: File) => {
    if (!allowReplacement()) return;
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
      // External-store updates may flush before React's imported/session state.
      const previousOwnership = ownedRecord.current;
      ownedRecord.current = false;
      const r = store.importRecord(text);
      if (!r.ok) ownedRecord.current = previousOwnership;
      if (r.ok) {
        setResultDismissed(false);
        collection.current?.begin(false);
        aiRef.current?.journal.clear();
      }
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
  const phaseText = snap.ply < snap.moveCount ? `履歴 ${snap.ply}/${snap.moveCount}手${snap.terminalFinished ? '・終局済み' : ''}` : { paused: '一時停止中', waiting: '次の着手待ち', thinking: `${snap.side === 'b' ? '先手' : '後手'} ${difficulty[snap.side] === 'model' ? 'モデル準備・思考中…' : `${difficulty[snap.side] === 'normal' ? 'Normal' : 'Easy'} 思考中…`}`,
    human: '人間の手番', history: '履歴表示中：分岐は専用ボタンから', finished: '対局終了', error: 'AIエラー' }[aiStatus.phase];

  const sideHands = (c: Color) => <Hands snap={snap} color={c} selection={selection} interactive={humanTurn} onHand={onHand} />;

  const openMatch = (kind: 'watch' | 'human') => {
    setMatchKind(kind); setDraftMode(mode === 'r-r' ? 'h-r' : mode);
    setDraftOpponent(difficulty[mode === 'r-h' ? 'b' : 'w']); setSheet('match');
  };
  const startMatch = () => {
    const nextMode = matchKind === 'watch' ? 'r-r' : draftMode;
    if (nextMode !== 'r-r' && draftOpponent === 'model' && !library.entries.length) return;
    if (!reset(nextMode)) return;
    if (nextMode !== 'r-r') {
      const side = nextMode === 'h-r' ? 'w' : 'b';
      if (draftOpponent === 'model') {
        const first=library.entries.find(entry => entry.sourceId === library.choices[side]?.sourceId) ?? library.entries[0]!;
        const precision = first.model.variants.some(v => v.precision === draftPrecision) ? draftPrecision : first.model.variants[0]!.precision;
        setLibrary(chooseModel(library,side,{ sourceId:first.sourceId,precision,backend:'wasm' }));
      }
      setDifficulty(previous => ({ ...previous, [side]: draftOpponent }));
    }
    setView(nextMode === 'r-r' ? 'both' : '2d'); setRunning(true); setSheet(null);
  };
  const goto = (ply: number) => { pause(); store.goto(ply); if (mode !== 'r-r' && ply === snap.moveCount && !(snap.terminalFinished ?? snap.finished)) setRunning(true); };
  const branchGame = () => {
    if (!window.confirm('この局面から新しい対局へ分岐します。元の棋譜は必要なら先に保存してください。続けますか？')) return false;
    pause();
    try {
      const source = JSON.parse(store.exportRecord());
      const wasOwned=ownedRecord.current; ownedRecord.current=false;
      let result: ReturnType<GameStore['importRecord']>;
      try { result = store.importRecord(JSON.stringify({ ...source, moves: source.moves.slice(0,snap.ply), result: null, termination: null })); }
      finally { ownedRecord.current=wasOwned; }
      if (!result.ok) { setMessage(`分岐できません: ${result.error}`); return false; }
      collection.current?.begin(wasOwned,snap.ply);
      setResultDismissed(false);
      aiRef.current?.journal.clear();
      setRunning(mode !== 'r-r'); return true;
    } catch { setMessage('棋譜を分岐できません'); return false; }
  };
  const stepOnce = () => {
    if (stepBusy) return;
    if (snap.ply < snap.moveCount && !branchGame()) return;
    aiRef.current?.step();
  };
  const previousMove = snap.lastMove ? parseMove(snap.lastMove) : null;
  const seatName = (side: Color) => {
    if (MODES[mode][side] === 'human') return 'あなた';
    if (difficulty[side] === 'easy') return 'Easy · ランダム';
    if (difficulty[side] === 'normal') return 'Normal · 探索';
    const selection = modelSeat(library, side)?.selection;
    return selection?.modelId === 'voxelshogi-transformer-s-m6-314159-v1'
      ? `学習済みS · ${selection.precision.toUpperCase()}${selection.precision === 'fp32' ? '' : '（重み）'}` : selection?.modelId ?? '学習済みS';
  };
  const terminalResult = snap.terminalResult ?? snap.result;
  const terminalFinished = snap.terminalFinished ?? snap.finished;

  return <div className="app arena-app">
    <header className="masthead"><h1>VoxelShogi <span>9×9×9</span></h1>
      <nav aria-label="メニュー"><button type="button" onClick={() => setSheet('models')}>モデル</button><button type="button" onClick={() => setSheet('record')}>棋譜</button><button type="button" onClick={() => setSheet('settings')}>対局設定</button></nav>
    </header>
    <nav className="entry-tabs" aria-label="遊び方"><button type="button" aria-pressed={mode === 'r-r'} onClick={() => { if (mode !== 'r-r') openMatch('watch'); }}>AIを観戦</button><button type="button" aria-pressed={mode !== 'r-r'} onClick={() => openMatch('human')}>AIと対戦</button></nav>
    <section className="intro" aria-label="このデモについて"><div><h2>次の一手は、別の層へ。</h2><p>9層の将棋。相手の玉を詰ませると勝ちです。</p></div>
      <div className="seats" aria-label="対戦するAIとプレイヤー">{(['b','w'] as const).map(side => <button type="button" className={`seat seat-${side}`} key={side} onClick={() => setSheet('research')}><b>{side === 'b' ? '☗先手' : '☖後手'}</b><span>{seatName(side)}</span></button>)}</div>
    </section>
    <main className="arena-main">
      <section className="arena-board" aria-label="盤と観戦操作">
        <div className="stage-heading"><div className="view-switch" role="group" aria-label="盤面の表示"><button type="button" aria-pressed={view !== '2d'} onClick={() => setView('both')}>立体で眺める</button><button type="button" aria-pressed={view === '2d'} onClick={() => setView('2d')}>断面を読む</button><button type="button" className="ghost" onClick={() => setSheet('display')}>表示設定</button></div><label className="mobile-layer"><span className="sr-only">層</span><select aria-label="表示する層" value={layers.z} onChange={e => { const z=Number(e.target.value); manualView(); setSlice({ axis: 'z', index:z }); setLayers({ ...layers,z }); }}>{ROMAN.map((label,z) => <option key={label} value={z}>{label}層</option>)}</select></label></div>
        <div className="move-banner"><p data-testid="last-move" role="status">{snap.lastMove ? `直前手：${snap.side === 'w' ? '☗先手' : '☖後手'} ${formatMove(snap.lastMove)}` : '開始局面：観戦を始めると、ここに着手を表示します。'}</p><span className="status" data-testid="status" role="status">{status}</span><p data-testid="ai-phase">{phaseText}</p></div>
        {message && <div className="message" role="alert"><span>{message}</span><button type="button" aria-label="メッセージを閉じる" onClick={() => setMessage(null)}>×</button></div>}
        {aiStatus.error && <div role="alert" data-testid="ai-error">{aiStatus.error}<button type="button" data-testid="ai-retry" onClick={() => aiRef.current?.retry()}>再試行</button><button type="button" onClick={() => openMatch(mode === 'r-r' ? 'watch' : 'human')}>別のAIで新規対局</button></div>}
        <div className={`views views-${view}`}>
          {view !== '2d' && <BoardFrame on2D={() => setView('2d')}><Suspense fallback={<p className="board3d-loading">3D盤面を読み込み中…<button type="button" onClick={() => setView('2d')}>2Dで続ける</button></p>}><Board3D snap={snap} selection={selection} view={layers} showTrail={trail} onSquare={onSquare} /></Suspense></BoardFrame>}
          {view !== '3d' && <div className="slice-board">{sideHands('w')}<Board2D snap={snap} slice={slice} selection={selection} interactive={humanTurn} onSquare={onSquare} />{sideHands('b')}</div>}
        </div>
        <div className="layer-rail" style={{ gridRow: 4 }} role="group" aria-label="注目する層">{ROMAN.map((label,z) => {
          const from = previousMove?.from !== null && previousMove?.from !== undefined && coordsOf(previousMove.from).z === z;
          const to = previousMove !== null && coordsOf(previousMove.to).z === z;
          return <button key={z} type="button" aria-label={`${label}層を見る${from ? '、移動元' : ''}${to ? '、移動先' : ''}`} aria-pressed={layers.z === z} className={`${from ? 'layer-from' : ''} ${to ? 'layer-to' : ''}`} onClick={() => { manualView(); setSlice({ axis: 'z', index: z }); setLayers({ ...layers, z }); }}><span>{label}</span><small>{to ? '着地' : from ? '元' : targetCounts[z] ? `${targetCounts[z]}候補` : '層'}</small></button>;
        })}</div>
        <div className="mobile-layer-labels" style={{ gridRow: 4 }} aria-label="9層の位置">{ROMAN.map((label,z) => <span key={label} className={layers.z===z ? 'selected' : ''}>{label}</span>)}</div>
        <section className="watch playback" aria-label="観戦操作">
          <div className="row">
            <button type="button" data-testid="undo" onClick={() => goto(Math.max(0,snap.ply-1))} disabled={snap.ply === 0}>◀ 1手戻る</button>
            <button type="button" onClick={() => { if (running || stepBusy) pause(); else { if (snap.ply < snap.moveCount) store.goto(snap.moveCount); if (!terminalFinished) setRunning(true); } }} className="primary" data-testid="toggle-run" disabled={snap.finished}>{terminalFinished && snap.ply === snap.moveCount ? '対局終了' : running ? '一時停止' : stepBusy ? '思考を中断' : snap.ply < snap.moveCount ? terminalFinished ? '終局位置へ' : '最新局面から再開' : snap.moveCount === 0 && mode === 'r-r' ? '観戦を開始' : '再開'}</button>
            <button type="button" data-testid="ai-step" aria-label={snap.ply < snap.moveCount && mode !== 'r-r' ? 'この局面から対戦を分岐' : undefined} disabled={running || snap.finished || (controller === 'human' && snap.ply === snap.moveCount) || !!aiStatus.error} aria-disabled={stepBusy} onClick={() => { if (snap.ply < snap.moveCount && mode !== 'r-r') branchGame(); else stepOnce(); }}>{snap.ply < snap.moveCount ? mode === 'r-r' ? 'ここからAIで分岐' : 'ここから対戦を分岐' : '1手指す'}</button>
            <button type="button" data-testid="cancel-search" aria-disabled={aiStatus.phase !== 'thinking'} onClick={() => { if (aiStatus.phase === 'thinking') pause(); }}>思考を中断</button>
            <button type="button" data-testid="redo" onClick={() => goto(Math.min(snap.moveCount,snap.ply+1))} disabled={snap.ply === snap.moveCount}>1手進む ▶</button>
          </div>
          <div className="row playback-options"><label className="check"><input type="checkbox" data-testid="follow-move" checked={follow} onChange={event => { setSlice(slice); setLayers(layers); setFollow(event.target.checked); }} /> {follow ? '直前手の層を追う' : '手動表示・追従OFF'}</label><label>着手間の待ち時間 {delay}ms（思考時間は別）<input data-testid="move-delay" type="range" min={50} max={2000} step={50} value={delay} onChange={e => setDelay(Number(e.target.value))} /></label></div>
          <p className="muted follow-explanation">{follow ? '着手先の層へ自動で切り替えます。' : '手動表示中。追従をONにすると着手先へ戻ります。'}</p>
          {snap.ply < snap.moveCount && <p className="sr-only">履歴 {snap.ply} / {snap.moveCount}手{terminalFinished && <span> · {terminalResult ? resultText(terminalResult) : '中断した対局'}</span>}</p>}
        </section>
        {terminalFinished && snap.ply === snap.moveCount && !resultDismissed && <section className="game-result" aria-label="対局結果"><h2>{terminalResult ? resultText(terminalResult) : '対局中断'}</h2><div className="row"><button type="button" onClick={() => { if (reset()) setRunning(true); }}>同じ設定でもう一局</button><button type="button" onClick={() => goto(0)}>最初から振り返る</button><button type="button" onClick={exportRecord}>棋譜を保存</button><button type="button" onClick={() => setResultDismissed(true)}>盤面を見る</button></div></section>}
      </section>
      <aside className="match-detail" aria-label="局面の詳細"><h2>棋譜をたどる</h2><MoveList snap={snap} onGoto={goto} /><button type="button" onClick={() => setSheet('research')}>AIの詳細を見る</button><button type="button" onClick={() => setSheet('record')}>棋譜を保存・読み込み</button></aside>
    </main>
    <Sheet title={sheet === 'match' ? matchKind === 'human' ? 'AIと対戦' : 'AIを観戦' : sheet === 'display' ? '表示・操作の設定' : sheet === 'record' ? '棋譜' : sheet === 'models' ? 'モデル・研究' : sheet === 'research' ? 'AIの詳細' : '対局・AI設定'} open={sheet !== null} onClose={() => setSheet(null)}>
      <section hidden={sheet !== 'match'}>
        {matchKind === 'human' && <><label>あなたの先後<select value={draftMode} onChange={e => setDraftMode(e.target.value as Mode)}><option value="h-r">先手（最初に指す）</option><option value="r-h">後手（AIが先に指す）</option></select></label><label>相手のAI<select value={draftOpponent} onChange={e => setDraftOpponent(e.target.value as ArenaDifficulty)}><option value="easy">Easy（ランダム）</option><option value="normal">Normal（探索）</option><option value="model">学習済みS</option></select></label>
          {draftOpponent === 'model' && <><p className="muted">申請・ログイン不要。モデルは対局開始後に自動で読み込み、この端末で動きます。</p>{library.entries[0] && <label>モデルの精度形式<select value={library.entries[0].model.variants.some(v => v.precision === draftPrecision) ? draftPrecision : library.entries[0].model.variants[0]!.precision} onChange={event => setDraftPrecision(event.target.value as ModelChoice['precision'])}>{library.entries[0].model.variants.map(variant => <option key={variant.precision} value={variant.precision}>{variant.precision === 'fp32' ? 'FP32（標準）' : `${variant.precision.toUpperCase()}（重み）`}</option>)}</select></label>}</>}
        </>}
        {matchKind === 'watch' && <p>現在の先後AI設定で、新しい観戦を始めます。</p>}
        {draftOpponent === 'model' && !library.entries.length && <p role="status">{publicModelState === 'error' ? 'モデル情報を取得できませんでした。通信を確認して再試行してください。' : 'モデル情報を確認中…'}</p>}
        {draftOpponent === 'model' && publicModelState === 'error' && !library.entries.length && <button type="button" onClick={() => setPublicAttempt(value => value + 1)}>モデル情報を再取得</button>}
        <button type="button" className="primary" disabled={matchKind === 'human' && draftOpponent === 'model' && !library.entries.length} onClick={startMatch}>{matchKind === 'human' ? '対戦をはじめる' : '観戦をはじめる'}</button>
      </section>
      <section className="panel left" hidden={sheet !== 'settings' && sheet !== 'models'}>
        {!library.entries.length && <p role="status">{publicModelState === 'error' ? 'Sモデル情報を取得できませんでした。' : '公開Sモデルの情報を確認中…'}</p>}
        {!library.entries.length && publicModelState === 'error' && <button type="button" onClick={() => setPublicAttempt(value => value + 1)}>モデル情報を再取得</button>}
        <label>モード<select value={mode} onChange={e => reset(e.target.value as Mode)} data-testid="mode">{Object.entries(MODES).map(([key,value]) => <option key={key} value={key}>{value.label}</option>)}</select></label>
        <div className="row"><button type="button" onClick={() => reset()}>新規対局</button><button type="button" onClick={() => { pause(); store.resign(); }} disabled={!humanTurn}>投了</button></div>
          <button type="button" onClick={() => setShowModels(!showModels)}>{showModels ? 'モデル読み込みを閉じる' : '学習済みモデルを読み込む'}</button>
          {showModels && <Suspense fallback={<p>読み込み中…</p>}><ModelLibraryPanel onLoaded={loadedModel} /></Suspense>}
          {library.entries.map(entry => <p className="muted model-source" key={entry.sourceId}>
            {entry.release.id}<br />SHA-256: {entry.release.manifest.sha256}<br />
            <button type="button" aria-label="モデルを外す" onClick={() => {
              if (snap.moveCount > 0 && ((library.choices.b?.sourceId === entry.sourceId && difficulty.b === 'model') || (library.choices.w?.sourceId === entry.sourceId && difficulty.w === 'model')) && !reset()) return;
              pause();
              setDifficulty({ b: difficulty.b === 'model' && library.choices.b?.sourceId === entry.sourceId ? 'normal' : difficulty.b, w: difficulty.w === 'model' && library.choices.w?.sourceId === entry.sourceId ? 'normal' : difficulty.w });
              setLibrary(removeModel(library, entry.sourceId));
            }}>モデルを外す</button>
          </p>)}
          {(['b', 'w'] as const).map((side) => <div key={side}><label>
            {side === 'b' ? '☗先手' : '☖後手'}のAI
            <select value={difficulty[side]} disabled={MODES[mode][side] === 'human'} data-testid={`difficulty-${side}`}
              onChange={(e) => selectDifficulty(side, e.target.value as ArenaDifficulty)}>
              <option value="easy">Easy（ランダム）</option><option value="normal">Normal（探索）</option>
              <option value="model" disabled={!library.entries.length}>学習済みモデル</option>
            </select>
          </label>
          {difficulty[side] === 'model' && library.choices[side] && <fieldset disabled={MODES[mode][side] === 'human'}>
            <legend>{side === 'b' ? '先手' : '後手'}のモデル条件</legend>
            <label>モデル<select data-testid={`model-${side}`} value={library.choices[side].sourceId} onChange={event => {
              const entry = library.entries.find(item => item.sourceId === event.target.value)!;
              choose(side, { ...library.choices[side]!, sourceId: entry.sourceId, precision: entry.model.variants[0]!.precision });
            }}>{library.entries.map(entry => <option key={entry.sourceId} value={entry.sourceId}>{entry.release.id}</option>)}</select></label>
            <label>精度形式<select data-testid={`precision-${side}`} value={library.choices[side].precision} onChange={event => choose(side, { ...library.choices[side]!, precision: event.target.value as ModelChoice['precision'] })}>
              {library.entries.find(entry => entry.sourceId === library.choices[side]!.sourceId)!.model.variants.map(variant => <option key={variant.precision} value={variant.precision}>{variant.precision === 'int8' ? 'INT8（重み）' : fp16WeightOnly(variant) ? 'FP16（重み）' : variant.precision.toUpperCase()}</option>)}
            </select></label>
            <label>実行先<select data-testid={`backend-${side}`} value={library.choices[side].backend} onChange={event => choose(side, { ...library.choices[side]!, backend: event.target.value as ModelChoice['backend'] })}>
              <option value="wasm">WASM（CPU）</option><option value="webgpu">WebGPU</option>
            </select></label>
            <p className="muted">対応しない形式・実行先は開始時に理由を表示します。</p>
          </fieldset>}
          </div>)}
          <label>Normalの思考上限
            <select value={budgetMs} data-testid="thinking-budget" onChange={(e) => { if (snap.moveCount > 0 && !reset()) return; pause(); setBudgetMs(Number(e.target.value)); }}>
              <option value={100}>0.1秒</option><option value={1000}>約1秒</option><option value={3000}>約3秒</option>
            </select>
          </label>
          <p className="muted">Normalは最大6手先・50,000ノード。<a href="/build-info.json" target="_blank" rel="noreferrer">実装バージョン</a></p>

      </section>
      <section hidden={sheet !== 'record'}>
          <MoveList snap={snap} testId="record-move-list" onGoto={ply => { goto(ply); setSheet(null); }} />
          <p className="muted">「保存」は端末へのJSONダウンロードです。</p>
          <div className="row">
            <button type="button" onClick={exportRecord}>
              保存
            </button>
            <button type="button" data-testid="export-ai-record" onClick={() => void exportConditions()}>棋譜＋AI条件</button>
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

      </section>
      <section className="panel right" hidden={sheet !== 'display'}>
        <section>
          <h2>表示</h2>
          <div className="row" role="group" aria-label="表示モード">
            {(['both', '3d', '2d'] as const).map((v) => (
              <button key={v} type="button" className={view === v ? 'primary' : ''} aria-pressed={view === v} onClick={() => setView(v)}>
                {{ both: '3D+2D', '3d': '3D', '2d': '2D' }[v]}
              </button>
            ))}
          </div>
        </section>
        <section>
          <h2>3D 層の表示</h2>
          <label className="check"><input type="checkbox" checked={trail} onChange={event => setTrail(event.target.checked)} />直前手の軌跡を表示</label>
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
                manualView();
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
                onClick={() => { manualView(); setSlice({ axis: a, index: slice.index }); }}
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
                manualView();
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

      </section>
      <section hidden={sheet !== 'research' && sheet !== 'models'}><p>学習済みSは申請・ログイン不要で対戦・観戦できます。Easyはランダム、Normalは探索AIです。Sの棋力向上は未確認です。</p>
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
        {ARENA_LINKS.map(link => <p key={link.href}><a href={link.href}>{link.label}</a></p>)}<a href="/privacy.html">プライバシー</a>
      </section>
    </Sheet>
    {promotion && <PromotionDialog onChoose={promote => play(promote ? promotion.promote : promotion.plain)} onCancel={() => { setPromotion(null); setSelection(NO_SELECTION); }} />}
  </div>;
}
