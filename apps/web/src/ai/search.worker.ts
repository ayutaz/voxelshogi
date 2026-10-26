import init from '../wasm/pkg/voxelshogi_wasm.js';
import wasmUrl from '../wasm/pkg/voxelshogi_wasm_bg.wasm?url';
import { SearchEngine } from './search-engine';

const engine = new SearchEngine(async () => { await init({ module_or_path: wasmUrl }); });
self.onmessage = (event: MessageEvent<unknown>) => {
  // Dedicated Worker ports leave MessageEvent.origin empty (HTML message port
  // post message steps). This is not a Window.postMessage endpoint.
  if (event.origin !== '') return;
  void engine.run(event.data).then((reply) => self.postMessage(reply));
};
