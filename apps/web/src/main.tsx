import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import init from './wasm/pkg/voxelshogi_wasm.js';
import wasmUrl from './wasm/pkg/voxelshogi_wasm_bg.wasm?url';
import { App } from './App';
import './styles.css';

const root = createRoot(document.getElementById('root')!);

init({ module_or_path: wasmUrl })
  .then(() =>
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    ),
  )
  .catch((e: unknown) => {
    root.render(<p className="fatal">エンジンの読み込みに失敗しました: {String(e)}</p>);
  });
