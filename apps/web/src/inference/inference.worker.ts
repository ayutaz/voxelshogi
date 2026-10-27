import { InferenceEngine, parseInferenceRequest, type InferenceRequest } from './engine';

let active: InferenceRequest | null = null;
const engine = new InferenceEngine(undefined, (phase) => {
  if (active) self.postMessage({ kind: 'progress', request: active, phase, atUnixMs: performance.timeOrigin + performance.now() });
});
self.onmessage = (event: MessageEvent<unknown>) => {
  if (event.origin !== '') return; // Dedicated Worker port, not Window.postMessage.
  let request: InferenceRequest;
  try { request = parseInferenceRequest(event.data); }
  catch { return; }
  if (active) { self.postMessage({ kind: 'error', request, message: 'inference engine busy' }); return; }
  active = request;
  void engine.infer(request).then((result) => self.postMessage({ kind: 'result', result }))
    .catch((error: unknown) => self.postMessage({ kind: 'error', request, message: (error instanceof Error ? error.message : String(error)).slice(0, 500) }))
    .finally(() => { active = null; });
};
