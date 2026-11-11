// Self-contained so Playwright can serialize this function into the loopback page.
// The fixed case deadline is never renewed by progress messages.
export function runResearchCase(data, options = {}) {
  const createWorker = options.createWorker ?? (() => new Worker('/worker.mjs', { type: 'module' }));
  const schedule = options.setTimeout ?? globalThis.setTimeout;
  const cancel = options.clearTimeout ?? globalThis.clearTimeout;
  const publish = options.onProgress ?? (value => globalThis.__researchProgress?.(value));
  return new Promise(resolve => {
    const worker = createWorker(), progress = [];
    let finished = false;
    const finish = result => {
      if (finished) return;
      finished = true;cancel(timer);worker.terminate();
      resolve({ ...result, name: data.name, backend: data.backend, progress: [...progress] });
    };
    const fail = (error_type, error_message) => finish({ status: 'failed', stage: progress.at(-1)?.stage ?? 'worker-start', error_type, error_message: String(error_message).slice(0, 1024) });
    const timer = schedule(() => fail('TimeoutError', 'research case timed out'), 180000);
    worker.onmessage = ({ data: message }) => {
      if (finished) return;
      if (message?.name !== data.name || message?.backend !== data.backend) { fail('ProtocolError', 'research case identity differs');return; }
      if (message.status === 'progress') {
        if (progress.length >= 128 || typeof message.stage !== 'string' || message.stage.length < 1 || message.stage.length > 64 || !Number.isFinite(message.elapsed_ms) || message.elapsed_ms < (progress.at(-1)?.elapsed_ms ?? 0)) {
          fail('ProtocolError', 'invalid or excessive research progress');return;
        }
        const update = { name: message.name, backend: message.backend, stage: message.stage, elapsed_ms: message.elapsed_ms, sequence: progress.length + 1 };
        for (const key of ['fixture_id', 'step']) if (message[key] !== undefined) update[key] = message[key];
        progress.push(update);
        try {
          Promise.resolve(publish(update)).catch(error => fail('ProgressError', error.message));
        } catch (error) { fail('ProgressError', error.message); }
        return;
      }
      if (!['success', 'failed'].includes(message.status)) { fail('ProtocolError', 'unknown research terminal status');return; }
      finish(message);
    };
    worker.onerror = error => fail('WorkerError', error.message);
    try { worker.postMessage(data); } catch (error) { fail('TransportError', error.message); }
  });
}
