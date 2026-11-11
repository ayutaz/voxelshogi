import assert from 'node:assert/strict';
import test from 'node:test';
import { runResearchCase } from '../research-browser-channel.mjs';

function setup() {
  const timers = [], cleared = [], progress = [];
  const worker = { terminated: 0, sent: [], terminate() { this.terminated++; }, postMessage(value) { this.sent.push(value); } };
  const data = { name: 'axial', backend: 'wasm', plan: { warmup_steps: 8, measured_steps: 32 } };
  const promise = runResearchCase(data, { createWorker: () => worker,
    setTimeout: (callback, milliseconds) => { timers.push({ callback, milliseconds });return 17; },
    clearTimeout: id => cleared.push(id), onProgress: value => progress.push(value) });
  const emit = value => worker.onmessage({ data: { name: 'axial', backend: 'wasm', ...value } });
  return { timers, cleared, progress, worker, promise, data, emit };
}

test('progress is retained without completing the case or resetting its absolute timer', async () => {
  const s = setup();let resolved = false;s.promise.then(() => { resolved = true; });
  s.emit({ status: 'progress', stage: 'runtime', elapsed_ms: 0 });
  s.emit({ status: 'progress', stage: 'session', elapsed_ms: 25 });
  await Promise.resolve();
  assert.equal(resolved, false);
  assert.equal(s.worker.terminated, 0);
  assert.deepEqual(s.cleared, []);
  assert.equal(s.timers.length, 1);
  assert.equal(s.timers[0].milliseconds, 180000);
  assert.deepEqual(s.worker.sent, [s.data]);
  assert.deepEqual(s.progress.map(p => p.stage), ['runtime', 'session']);
  s.emit({ status: 'success', fixtures: ['terminal-proof'], session_released: true });
  const result = await s.promise;
  assert.equal(result.status, 'success');
  assert.deepEqual(result.fixtures, ['terminal-proof']);
  assert.deepEqual(result.progress, s.progress);
  assert.equal(s.worker.terminated, 1);
  assert.deepEqual(s.cleared, [17]);
});

test('timeout preserves the last actual stage and all earlier progress', async () => {
  const s = setup();
  s.emit({ status: 'progress', stage: 'model-download', elapsed_ms: 40 });
  s.emit({ status: 'progress', stage: 'session', elapsed_ms: 80 });
  s.timers[0].callback();
  const result = await s.promise;
  assert.equal(result.status, 'failed');
  assert.equal(result.error_type, 'TimeoutError');
  assert.equal(result.error_message, 'research case timed out');
  assert.equal(result.stage, 'session');
  assert.deepEqual(result.progress.map(p => p.elapsed_ms), [40, 80]);
  assert.equal(s.worker.terminated, 1);
  s.emit({ status: 'success' });
  assert.equal(s.worker.terminated, 1);
});

test('timeout before any worker response remains distinguishable from model/session work', async () => {
  const s = setup();s.timers[0].callback();
  assert.equal((await s.promise).stage, 'worker-start');
});

test('worker execution errors retain the last stage and release the worker', async () => {
  const s = setup();s.emit({ status: 'progress', stage: 'measurement', elapsed_ms: 100, fixture_id: 3, step: 9 });
  s.worker.onerror({ message: 'fake GPU device lost' });
  const result = await s.promise;
  assert.equal(result.status, 'failed');assert.equal(result.error_type, 'WorkerError');
  assert.equal(result.stage, 'measurement');assert.match(result.error_message, /GPU device lost/);
  assert.equal(result.progress[0].fixture_id, 3);assert.equal(result.progress[0].step, 9);
  assert.equal(s.worker.terminated, 1);
});

test('cross-case progress and malformed terminal states cannot complete another matrix cell', async () => {
  for (const message of [{ status: 'progress', name: 'full', stage: 'session', elapsed_ms: 0 }, { status: 'unknown' }, { status: 'success', backend: 'webgpu' }]) {
    const s = setup();s.emit(message);
    assert.equal(s.worker.terminated, 1);
    const result = await s.promise;
    assert.equal(result.status, 'failed');assert.equal(result.error_type, 'ProtocolError');
    assert.equal(s.worker.terminated, 1);
  }
});

test('progress count is bounded and malformed progress fails rather than growing metadata', async () => {
  const s = setup();
  for (let i = 0; i < 129; i++) s.emit({ status: 'progress', stage: 'warmup', elapsed_ms: i });
  assert.equal(s.worker.terminated, 1);
  const result = await s.promise;
  assert.equal(result.error_type, 'ProtocolError');assert.equal(result.progress.length, 128);
  for (const bad of [{ stage: '', elapsed_ms: 0 }, { stage: 'session', elapsed_ms: NaN }, { stage: 'session', elapsed_ms: -1 }]) {
    const s = setup();s.emit({ status: 'progress', ...bad });
    assert.equal((await s.promise).error_type, 'ProtocolError');
  }
});

test('the function works after serialization into a browser-like global scope', async () => {
  const vm = await import('node:vm');let worker, timer, published;
  class Worker {
    constructor(url, options) { assert.equal(url, '/worker.mjs');assert.equal(options.type, 'module');worker = this; }
    postMessage(data) { this.data = data; }
    terminate() { this.terminated = true; }
  }
  const run = vm.runInNewContext(`(${runResearchCase.toString()})`, { Worker, setTimeout: callback => { timer = callback;return 1; }, clearTimeout: () => {}, __researchProgress: value => { published = value; } });
  const promise = run({ name: 'cnn', backend: 'webgpu' });
  worker.onmessage({ data: { name: 'cnn', backend: 'webgpu', status: 'progress', stage: 'runtime', elapsed_ms: 0 } });
  assert.equal(published.stage, 'runtime');assert.equal(published.sequence, 1);
  timer();const result = await promise;
  assert.equal(result.error_type, 'TimeoutError');assert.equal(result.stage, 'runtime');assert.equal(worker.terminated, true);
});
