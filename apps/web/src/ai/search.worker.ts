import init from '../wasm/pkg/voxelshogi_wasm.js';
import wasmUrl from '../wasm/pkg/voxelshogi_wasm_bg.wasm?url';
import { SearchEngine } from './search-engine';

const engine = new SearchEngine(async () => { await init({ module_or_path: wasmUrl }); });
self.onmessage = (event: MessageEvent<unknown>) => {
  void engine.run(event.data).then((reply) => self.postMessage(reply));
};
