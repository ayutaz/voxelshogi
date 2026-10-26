import { useEffect, useMemo, useState } from 'react';
import { ExperimentReplay } from '../wasm/pkg/voxelshogi_wasm.js';
import { Board3D } from '../renderer/Board3D';
import { Board2D } from '../components/Board2D';
import { coordsOf, formatMove, parseMove, decodePiece } from '../game/model';
import type { BoardSnapshot } from '../game/boardSnapshot';
import { verifyDigest } from './integrity';
import './experiment.css';

type Rule = 'voxelshogi-nine-kings-first5-v0' | 'voxelshogi-nine-kings-all-v0' | 'voxelshogi-nine-kings-score-v0';
const titles: Record<Rule, string> = {
  'voxelshogi-nine-kings-first5-v0': '5王先取',
  'voxelshogi-nine-kings-all-v0': '全9王捕獲',
  'voxelshogi-nine-kings-score-v0': '規定手数・得点比較',
};
interface Entry {
  id: Rule;
  file: string;
  sha256: string;
  sample: { seed: number; swapped: boolean; plies: number; kingCapturePlies: number[] };
  summary: {
    games: number;
    wins: { Black: number; White: number; draw: number };
    reasons: Record<string, number>;
    meanCapturedKings: number;
  };
}
interface Manifest {
  engine: string;
  search: { depth: number; width: number };
  maxPlies: number;
  entries: Entry[];
}
interface RecordInfo {
  ruleset_id: string;
  max_plies: number;
  search: { depth: number; width: number };
  moves: string[];
  seed: number;
  swapped: boolean;
  engine: string;
}
interface Frame {
  board: number[];
  hands: number[][];
  ply: number;
  hash: string;
  side: 'b' | 'w';
  captured: number[];
  lastMove: string | null;
  kingCapture: boolean;
  outcome: { winner: 'Black' | 'White' | null; reason: string } | null;
}
const reasonNames: Record<string, string> = {
  target: '目標捕獲数に到達',
  score_limit: '規定手数の得点比較',
  move_limit: '実験上限で打ち切り',
  repetition: '千日手',
  no_moves: '合法手なし',
};
const noSelection = { type: 'none' } as const;
const noPick = () => {};
const experimentCamera: [number, number, number] = [0, 18, 25];
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];

export default function ExperimentViewer() {
  const [study, setStudy] = useState<'main' | 'long'>('main');
  const base = study === 'long' ? '/experiments/long/' : '/experiments/';
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [rule, setRule] = useState<Rule>('voxelshogi-nine-kings-first5-v0');
  const [error, setError] = useState('');
  useEffect(() => {
    const abort = new AbortController();
    fetch(`${base}manifest.json`, { signal: abort.signal, cache: 'no-cache' })
      .then(async (r) => {
        if (!r.ok) throw Error('比較結果を読み込めません');
        const m = (await r.json()) as Manifest;
        if (m.entries.length !== 3 || m.entries.some((e) => !titles[e.id])) throw Error('比較結果の形式が違います');
        setManifest(m);
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted) setError(String(e));
      });
    return () => abort.abort();
  }, [base]);
  const entry = manifest?.entries.find((e) => e.id === rule);
  return (
    <div className="experiment">
      <header>
        <div>
          <span className="experiment-eyebrow">VOXELSHOGI / RULE EXPERIMENT</span>
          <h1>9王ルール比較室</h1>
        </div>
        <a href="/">通常の対局画面へ</a>
      </header>
      <div className="experiment-intro">
        <p>どの勝利条件が、眺めて楽しいか。</p>
        <span>同じ初期配置・同じ探索条件で比較。表示A/Bは同じ棋譜を再生します。</span>
      </div>
      <div className="experiment-study">
        <label>
          比較条件
          <select
            aria-label="比較条件"
            value={study}
            onChange={(e) => {
              setManifest(null);
              setError('');
              setStudy(e.target.value as 'main' | 'long');
            }}
          >
            <option value="main">主試験：400手・各200局</option>
            <option value="long">延長試験：800手・各40局（seed 0〜19）</option>
          </select>
        </label>
      </div>
      {error && (
        <p role="alert" className="message">
          {error}
        </p>
      )}
      {manifest && entry ? (
        <>
          <div className="experiment-rule">
            <label>
              比較するルール
              <select aria-label="比較するルール" value={rule} onChange={(e) => setRule(e.target.value as Rule)}>
                {manifest.entries.map((e) => (
                  <option key={e.id} value={e.id}>
                    {titles[e.id]}
                  </option>
                ))}
              </select>
            </label>
            <p>
              探索AI試作・学習モデル未使用
              <br />
              <small>CPUで生成した実際の棋譜を再生。ブラウザ内のライブ対局ではありません。</small>
            </p>
          </div>
          <RecordLoader key={`${study}:${entry.id}`} entry={entry} manifest={manifest} base={base} />
        </>
      ) : (
        !error && <p className="fatal">比較結果を読み込み中…</p>
      )}
    </div>
  );
}

function RecordLoader({ entry, manifest, base }: { entry: Entry; manifest: Manifest; base: string }) {
  const [loaded, setLoaded] = useState<{ replay: ExperimentReplay; record: RecordInfo } | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const abort = new AbortController();
    let replay: ExperimentReplay | undefined;
    const load = async () => {
      const response = await fetch(`${base}${encodeURIComponent(entry.file)}`, {
        signal: abort.signal,
        cache: 'no-cache',
      });
      if (!response.ok) throw Error('棋譜を読み込めません');
      const text = await response.text();
      await verifyDigest(text, entry.sha256);
      if (abort.signal.aborted) return;
      const record = JSON.parse(text) as RecordInfo;
      if (
        record.ruleset_id !== entry.id ||
        record.engine !== manifest.engine ||
        record.max_plies !== manifest.maxPlies ||
        record.search.depth !== manifest.search.depth ||
        record.search.width !== manifest.search.width
      )
        throw Error('棋譜と比較条件が一致しません');
      replay = new ExperimentReplay(text); // Rust validates every move, result and final hash.
      setLoaded({ replay, record });
    };
    load().catch((e: unknown) => {
      if (!abort.signal.aborted) setError(String(e));
    });
    return () => {
      abort.abort();
      replay?.free();
    };
  }, [entry, manifest, base]);
  if (error)
    return (
      <p role="alert" className="message">
        {error}
      </p>
    );
  if (!loaded) return <p className="fatal">棋譜を検証中…</p>;
  return <Playback {...loaded} entry={entry} manifest={manifest} base={base} />;
}

function Playback({
  replay,
  record,
  entry,
  manifest,
  base,
}: {
  replay: ExperimentReplay;
  record: RecordInfo;
  entry: Entry;
  manifest: Manifest;
  base: string;
}) {
  const [ply, setPly] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [interval, setIntervalMs] = useState(800);
  const [presentation, setPresentation] = useState<'overview' | 'focus'>('overview');
  const [manualLayer, setManualLayer] = useState(4);
  const frame = useMemo(() => JSON.parse(replay.snapshot(ply)) as Frame, [replay, ply]);
  const snap: BoardSnapshot = useMemo(
    () => ({
      board: new Uint8Array(frame.board),
      lastMove: frame.lastMove,
      inCheck: { b: false, w: false },
      kingSquare: { b: -1, w: -1 },
    }),
    [frame],
  );
  const autoLayer = frame.lastMove ? coordsOf(parseMove(frame.lastMove).to).z : 4;
  const layer = presentation === 'focus' ? autoLayer : manualLayer;
  const target = entry.id.includes('first5') ? 5 : entry.id.includes('-all-') ? 9 : null;
  const goal = target ? `相手の王を${target}枚取れば勝ち` : `${manifest.maxPlies}手で、取った王が多い側の勝ち`;
  const nextCapture = entry.sample.kingCapturePlies.find((p) => p > ply);
  const last = frame.lastMove ? formatMove(frame.lastMove) : '初期局面';
  const jump = (p: number) => {
    setPlaying(false);
    setPly(p);
  };
  useEffect(() => {
    if (!playing || ply >= record.moves.length) return;
    const timer = window.setTimeout(() => setPly((p) => Math.min(p + 1, record.moves.length)), interval);
    return () => window.clearTimeout(timer);
  }, [playing, ply, interval, record.moves.length]);
  const active = playing && ply < record.moves.length;
  return (
    <>
      <div className="experiment-layout">
        <aside className="experiment-sidebar">
          <span className="experiment-tag">RULE {manifest.entries.indexOf(entry) + 1} / 03</span>
          <h2>{titles[entry.id]}</h2>
          <p className="experiment-goal">{goal}</p>
          <p className="muted">各9王から開始。王手の強制応手はありません。取った王は復活しません。</p>
          <div className="experiment-scores">
            {(['先手', '後手'] as const).map((name, i) => (
              <div className={`experiment-score side-${i}`} key={name}>
                <span>{name}が取った王</span>
                <strong>
                  {frame.captured[i]}
                  <small>{target ? ` / ${target}` : ' 枚'}</small>
                </strong>
                <div className="king-track" aria-hidden>
                  {Array.from({ length: target ?? 9 }, (_, n) => (
                    <i key={n} className={n < frame.captured[i]! ? 'taken' : ''} />
                  ))}
                </div>
                <small>自分の王：残り{9 - frame.captured[1 - i]!}枚</small>
              </div>
            ))}
          </div>
          <p data-testid="experiment-result" className="experiment-result">
            {frame.outcome
              ? `${frame.outcome.winner ? (frame.outcome.winner === 'Black' ? '先手の勝ち' : '後手の勝ち') : '引き分け'}・終局（${reasonNames[frame.outcome.reason]}）`
              : `${frame.side === 'b' ? '先手' : '後手'}の番`}
          </p>
          <section className="experiment-measure">
            <h3>同条件の実測 {entry.summary.games}局</h3>
            <p>
              先手勝ち {entry.summary.wins.Black} / 後手勝ち {entry.summary.wins.White}
              <br />
              引き分け {entry.summary.wins.draw}
            </p>
            <p>
              目標到達 {entry.summary.reasons.target ?? 0}局<br />
              上限打ち切り {entry.summary.reasons.move_limit ?? 0}局<br />
              得点比較で終了 {entry.summary.reasons.score_limit ?? 0}局<br />
              平均の王捕獲 合計{entry.summary.meanCapturedKings.toFixed(2)}枚
            </p>
            <small>面白さの評価や、人によるA/B評価は未実施です。</small>
          </section>
        </aside>
        <section className="experiment-stage">
          <div className="experiment-display">
            <label>
              観戦表示
              <select
                aria-label="観戦表示"
                value={presentation}
                onChange={(e) => setPresentation(e.target.value as 'overview' | 'focus')}
              >
                <option value="overview">A：全体を眺める</option>
                <option value="focus">B：着手と捕獲を追う</option>
              </select>
            </label>
            <span>{presentation === 'overview' ? '全9層を表示' : `${ROMAN[layer]}層を自動で注目`}</span>
          </div>
          <Board3D
            snap={snap}
            selection={noSelection}
            onSquare={noPick}
            view={{ mode: presentation === 'overview' ? 'all' : 'focus', z: layer, dim: 0.07 }}
            showTrail={presentation === 'focus'}
            cameraPosition={experimentCamera}
          />
          <div className="experiment-caption">
            <span>直前の着手：{last}</span>
            {presentation === 'focus' && frame.kingCapture && (
              <strong data-testid="king-event">王を捕獲 · {frame.side === 'w' ? '先手' : '後手'}に1点</strong>
            )}
          </div>
          <div className="experiment-controls">
            <div className="row">
              <button onClick={() => jump(0)} disabled={ply === 0}>
                初期局面
              </button>
              <button onClick={() => jump(ply - 1)} disabled={ply === 0}>
                1手戻る
              </button>
              <button
                className="primary"
                onClick={() => {
                  if (ply === record.moves.length) setPly(0);
                  setPlaying(!active);
                }}
              >
                {active ? '一時停止' : '再生'}
              </button>
              <button onClick={() => jump(ply + 1)} disabled={ply === record.moves.length}>
                1手進む
              </button>
              <button onClick={() => jump(nextCapture!)} disabled={nextCapture === undefined}>
                次の王捕獲
              </button>
              <button onClick={() => jump(record.moves.length)} disabled={ply === record.moves.length}>
                最終局面
              </button>
            </div>
            <label>
              局面 <b data-testid="experiment-ply">{ply}</b> / {record.moves.length} 手
              <input
                aria-label="再生位置"
                type="range"
                min="0"
                max={record.moves.length}
                value={ply}
                onChange={(e) => jump(Number(e.target.value))}
              />
            </label>
            <label>
              再生間隔
              <select aria-label="再生間隔" value={interval} onChange={(e) => setIntervalMs(Number(e.target.value))}>
                <option value="200">0.2秒 / 手</option>
                <option value="800">0.8秒 / 手</option>
                <option value="1600">1.6秒 / 手</option>
              </select>
            </label>
            <small>
              1手 = 1 ply。{manifest.maxPlies}手の上限は先後各{manifest.maxPlies / 2}
              着手。再生速度はAIの思考時間と別です。
            </small>
          </div>
        </section>
        <aside className="experiment-detail">
          <h3>注目層の断面</h3>
          <Board2D snap={snap} slice={{ axis: 'z', index: layer }} selection={noSelection} onSquare={noPick} />
          <label>
            断面の層 {ROMAN[layer]}
            <input
              aria-label="断面の層"
              type="range"
              min="0"
              max="8"
              value={layer}
              disabled={presentation === 'focus'}
              onChange={(e) => setManualLayer(Number(e.target.value))}
            />
          </label>
          <p className="muted">
            Bは着手先の層を自動選択。3D上の光が移動方向を示します。表示を切り替えても同じ局面を保ちます。
          </p>
          <h3>持ち駒</h3>
          {(['先手', '後手'] as const).map((name, i) => (
            <p key={name} className="muted">
              {name}：
              {frame.hands[i]!.map((count, kind) => (count ? `${decodePiece(kind + 1)!.label}${count}` : ''))
                .filter(Boolean)
                .join(' ') || 'なし'}
            </p>
          ))}
          <h3>このサンプル</h3>
          <p className="muted">
            打ち切りを含む全局から、対局長の中央値に最も近い棋譜を選択。同順位はseed順です。短い・派手な対局だけは選んでいません。
          </p>
          <details>
            <summary>再現条件と照合情報</summary>
            <p>
              両AI：深さ{manifest.search.depth}・候補幅{manifest.search.width}
              <br />
              seed {record.seed} / 先後交換 {record.swapped ? 'あり' : 'なし'}
            </p>
            <small>実装 {record.engine}</small>
            <p>
              棋譜 SHA-256
              <br />
              <code data-testid="record-hash">{entry.sha256}</code>
            </p>
            <p>
              局面ハッシュ
              <br />
              <code data-testid="position-hash">{frame.hash}</code>
            </p>
            <a href={`${base}${encodeURIComponent(entry.file)}`} download>
              この棋譜を保存
            </a>
          </details>
        </aside>
      </div>
      <footer>
        試作ルールの比較です。採用判断は保留中。ルールの比較には全局の実測を、表示の比較には同じ棋譜・同じ手数を使います。
      </footer>
    </>
  );
}
