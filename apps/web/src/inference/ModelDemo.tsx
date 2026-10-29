import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Game } from '../wasm/pkg/voxelshogi_wasm.js';
import { GameStore } from '../game/store';
import { Board2D } from '../components/Board2D';
import { NO_SELECTION } from '../game/interaction';
import { InferenceClient, type ClientResult, type Phase } from './client';
import { loadPackage, type ModelPackage } from './runtime';
import type { Backend, Precision } from './manifest';
import { assetUrl } from './assets';
import './model-demo.css';
import { MODEL_LINKS } from '../navigation';

const Board3D = lazy(() => import('../renderer/Board3D').then(m => ({ default: m.Board3D })));
const labels: Record<Precision, string> = { fp32: 'FP32', fp16: 'FP16', int8: 'INT8（重み）' };
const phaseLabels = { idle: '実行待ち', loading: 'モデルと実行環境を読み込み中', initializing: 'モデルを初期化中', running: '推論・数値照合中', done: '完了', cancelled: '中断しました', error: '実行に失敗しました' };
type State = keyof typeof phaseLabels;
const noPick = () => {};
const ms = (n: number) => `${n.toFixed(1)} ms`;

export default function ModelDemo() {
  const [pkg, setPackage] = useState<ModelPackage | null>(null);
  const [loadError, setLoadError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [variant, setVariant] = useState<Precision>('fp32');
  const [fixtureName, setFixture] = useState('initial-b');
  const [backend, setBackend] = useState<Backend>('wasm');
  const [state, setState] = useState<State>('idle');
  const [error, setError] = useState('');
  const [result, setResult] = useState<ClientResult | null>(null);
  const [show3D, setShow3D] = useState(true);
  const [layer, setLayer] = useState(4);
  const client = useRef<InferenceClient | null>(null);
  const generation = useRef(0);
  const revision = useRef(0);
  useEffect(() => {
    const instance = new InferenceClient(); client.current = instance;
    const requestGeneration = generation;
    return () => { requestGeneration.current++; instance.dispose(); if (client.current === instance) client.current = null; };
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    loadPackage(new URL('/models/m3/index.json', location.origin).href, abort.signal).then(p => {
      if (abort.signal.aborted) return;
      setPackage(p); setLoadError('');
      setVariant(p.model.variants[0]!.id); setFixture(p.model.fixtures[0]!.name);
    }).catch((e: unknown) => { if (!abort.signal.aborted) setLoadError(e instanceof Error ? e.message : String(e)); });
    return () => abort.abort();
  }, [attempt]);
  const fixture = pkg?.model.fixtures.find(f => f.name === fixtureName);
  const position = useMemo(() => {
    if (!fixture) return null;
    let game: Game | null = null;
    try { game = Game.fromRecordJson(JSON.stringify(fixture.record)); return { snapshot: new GameStore(game).snapshot(), error: '' }; }
    catch (e) { return { snapshot: null, error: e instanceof Error ? e.message : String(e) }; }
    finally { game?.free(); }
  }, [fixture]);
  const stop = (next: State) => {
    generation.current++; revision.current++; client.current?.cancel();
    setState(next); setResult(null); setError('');
  };
  const run = (iterations: 1 | 40) => {
    if (!pkg || !client.current || !position?.snapshot) return;
    const current = ++generation.current;
    setState('loading'); setResult(null); setError('');
    void client.current.infer({ revision: revision.current, packageHash: pkg.packageHash, variant, fixture: fixtureName, backend, iterations }, (phase: Phase) => {
      if (current === generation.current) setState(phase);
    }).then(reply => {
      if (current !== generation.current) return;
      setResult(reply); setState('done');
    }).catch((e: unknown) => {
      if (current !== generation.current) return;
      setError(e instanceof Error ? e.message : String(e)); setState('error');
    });
  };
  const busy = state === 'loading' || state === 'initializing' || state === 'running';
  const selected = pkg?.model.variants.find(v => v.id === variant);
  return <div className="model-demo">
    <header><h1>モデル推論ラボ</h1><nav>{MODEL_LINKS.map(link => <a key={link.href} href={link.href}>{link.label}</a>)}</nav></header>
    <p className="model-intro">未学習モデルの技術デモです。変換したモデルを、この端末のブラウザで実行します。棋力や勝率を示すものではありません。</p>
    {loadError ? <section><p role="alert">モデルを読み込めません：{loadError}</p><button onClick={() => { setLoadError(''); setAttempt(n => n + 1); }}>読み込みを再試行</button></section> : null}
    {!pkg && !loadError ? <p role="status">モデルの配布情報を確認中…</p> : null}
    {pkg ? <>
      <div className="model-layout">
        <aside className="model-controls">
          <h2>実行条件</h2>
          <label>精度形式<select aria-label="精度形式" value={variant} onChange={e => { stop('idle'); setVariant(e.target.value as Precision); }}>
            {pkg.model.variants.map(v => <option key={v.id} value={v.id}>{labels[v.id]}</option>)}
          </select></label>
          <label>実行先<select aria-label="実行先" value={backend} onChange={e => { stop('idle'); setBackend(e.target.value as Backend); }}>
            <option value="wasm">WASM（CPU）</option><option value="webgpu">WebGPU（GPU）</option>
          </select></label>
          <p className="muted">対応していない組み合わせは実行時に理由を表示します。実行先は自動で変更しません。</p>
          <label>検証局面<select aria-label="検証局面" value={fixtureName} onChange={e => { stop('idle'); setFixture(e.target.value); }}>
            {pkg.model.fixtures.map(f => <option key={f.name} value={f.name}>{f.name}</option>)}
          </select></label>
          <p data-testid="fixture-side">{position?.snapshot?.side === 'w' ? '後手' : '先手'}の視点・標準1王ルール</p>
          <div className="row"><button className="primary" onClick={() => run(1)} disabled={busy || !position?.snapshot}>推論を実行</button><button onClick={() => run(40)} disabled={busy || !position?.snapshot}>30回を計測</button><button data-testid="cancel-inference" onClick={() => stop('cancelled')} disabled={!busy}>中断</button></div>
          <p data-testid="inference-phase" data-phase={state} role="status">{phaseLabels[state]}</p>
          {error || position?.error ? <p role="alert">{error || position?.error}</p> : null}
          <small>反復計測は準備10回＋測定30回。推論と全出力の数値照合をWorkerで行います。条件変更は現在の要求を中断します。</small>
          <h2>配布モデル</h2>
          <p>{pkg.model.id}<br />{pkg.model.parameters.toLocaleString()} parameters / seed {pkg.model.seed}</p>
          <p>{labels[variant]}：{selected ? (selected.model.bytes / 1024 / 1024).toFixed(2) : '—'} MiB</p>
          {selected?.fp32Difference?.[fixtureName] ? <details><summary>FP32からの変化</summary><p>同じ変換版の実行誤差とは別の値です。未学習モデルの数値差で、棋力の比較ではありません。</p>{(['policy', 'value'] as const).map(name => {
            const difference = selected.fp32Difference![fixtureName]![name];
            return <p key={name}>{name}：最大絶対差 {difference.maxAbs.toExponential(3)} / 平均絶対差 {difference.mae.toExponential(3)} / RMSE {difference.rmse.toExponential(3)}</p>;
          })}</details> : null}
          {!pkg.index.publication ? <p className="model-local">ローカル検証用・公開前の配布物</p> : null}
          <details><summary>照合情報</summary><p>モデル情報 SHA-256<br /><code data-testid="model-hash">{pkg.packageHash}</code></p><p>選択モデル SHA-256<br /><code data-testid="variant-hash">{selected?.model.sha256}</code></p><p>ORT {pkg.index.runtime.version} / {pkg.model.license ?? '公開ライセンス未確定'}</p></details>
          {pkg.index.modelNotices.length ? <p>{pkg.index.modelNotices.map((file, index) => <span key={file.path}><a href={assetUrl(pkg.assetBase, file.path)} download>{index === 0 ? 'モデルのライセンス' : 'Model Card'}</a>{index === 0 ? ' / ' : ''}</span>)}</p> : null}
        </aside>
        <section className="model-stage">
          <div className="row"><label className="check"><input aria-label="3D表示" type="checkbox" checked={show3D} onChange={e => setShow3D(e.target.checked)} />3D表示</label><label>断面の層<input aria-label="断面の層" type="range" min="0" max="8" value={layer} onChange={e => setLayer(Number(e.target.value))} /></label></div>
          {position?.snapshot ? <>
            {show3D ? <Suspense fallback={<p>3D盤面を読み込み中…</p>}><Board3D snap={position.snapshot} selection={NO_SELECTION} onSquare={noPick} view={{ mode: 'focus', z: layer, dim: .12 }} /></Suspense> : null}
            <Board2D snap={position.snapshot} selection={NO_SELECTION} onSquare={noPick} slice={{ axis: 'z', index: layer }} />
          </> : null}
        </section>
      </div>
      {result ? <section data-testid="inference-result" data-backend={result.information.backend} className="model-result">
        <h2>実行結果</h2><p>実行先：{result.information.backend} / {labels[result.request.variant]} / {result.request.fixture}</p>
        <p>Value {result.value.toFixed(6)}（手番側の未学習出力）</p>
        <table><caption>同じ変換版の基準値との数値比較</caption><thead><tr><th>出力</th><th>照合要素数</th><th>最大絶対誤差</th><th>許容範囲外</th></tr></thead><tbody>{(['policy', 'value'] as const).map(name => <tr key={name}><th>{name}</th><td>{result.comparison[name].elements.toLocaleString()}</td><td>{result.comparison[name].maxAbs.toExponential(3)}</td><td>{result.comparison[name].exceeded}</td></tr>)}</tbody></table>
        <p>読込 {ms(result.metrics.loadMs)} / 初期化 {ms(result.metrics.initMs)} / {result.metrics.samples.length === 1 ? '推論' : '推論中央値'} {ms(result.metrics.medianMs)} / p95 {ms(result.metrics.p95Ms)} / Worker往復 {ms(result.roundTripMs)}</p>
        <p className="muted">推論時間はCPUへの出力読出しを含みます。全出力の照合時間はWorker往復に含まれます。</p>
        <details><summary>測定値と実行配置</summary><pre data-testid="inference-json">{JSON.stringify(result, null, 2)}</pre></details>
      </section> : null}
    </> : null}
  </div>;
}
