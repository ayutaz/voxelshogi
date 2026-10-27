import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import init from './wasm/pkg/voxelshogi_wasm.js';
import wasmUrl from './wasm/pkg/voxelshogi_wasm_bg.wasm?url';
import { App } from './App';
import './styles.css';

const ExperimentViewer = lazy(() => import('./experiment/ExperimentViewer'));
const ModelDemo = lazy(() => import('./inference/ModelDemo'));
const experiment = new URLSearchParams(location.search).has('experiment');
const models = new URLSearchParams(location.search).has('models');

const root = createRoot(document.getElementById('root')!);

init({ module_or_path: wasmUrl })
  .then(() =>
    root.render(
      <StrictMode>
        <Suspense fallback={<p className="fatal">画面を読み込み中…</p>}>{models ? <ModelDemo /> : experiment ? <ExperimentViewer /> : <App />}</Suspense>
      </StrictMode>,
    ),
  )
  .catch((e: unknown) => {
    root.render(<p className="fatal">エンジンの読み込みに失敗しました: {String(e)}</p>);
  });
