import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import init from './wasm/pkg/voxelshogi_wasm.js';
import wasmUrl from './wasm/pkg/voxelshogi_wasm_bg.wasm?url';
import { App } from './App';
import './styles.css';
import { screenForQuery } from './navigation';

const ModelDemo = lazy(() => import('./inference/ModelDemo'));
const screen = screenForQuery(location.search);

const root = createRoot(document.getElementById('root')!);

init({ module_or_path: wasmUrl })
  .then(() =>
    root.render(
      <StrictMode>
        <Suspense fallback={<p className="fatal">画面を読み込み中…</p>}>{screen === 'models' ? <ModelDemo /> : <App />}</Suspense>
      </StrictMode>,
    ),
  )
  .catch((e: unknown) => {
    root.render(<p className="fatal">エンジンの読み込みに失敗しました: {String(e)}</p>);
  });
