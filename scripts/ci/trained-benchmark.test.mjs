import assert from 'node:assert/strict';
import test from 'node:test';
import { fixedPositions, switchPrecisions, installPolicyBridge } from '../trained-benchmark.mjs';

test('fixed roots use replayed Rust metadata and preserve all history for each fixture', () => {
  let freed = 0;
  const manifest = { fixtures: [{ name: 'first', side: 'w', record: { moves: ['111211'] } }] };
  const result = fixedPositions(manifest, json => {
    assert.deepEqual(JSON.parse(json), { moves: ['111211'] });
    return { sideToMove: () => 'w', ply: () => 1, hash: () => '1234567890abcdef', legalMoves: () => ['999899'], free: () => freed++ };
  }, (move, side) => { assert.equal(move, '999899'); assert.equal(side, 'w'); return 1460; });
  assert.deepEqual(result, [{ name: 'first', root: { revision: 0, cursor: 1, side: 'w', hash: '1234567890abcdef', ruleset: 'voxelshogi-standard-v1', recordJson: '{"moves":["111211"]}' }, legal: [{ move: '999899', action: 1460 }] }]);
  assert.equal(freed, 1);
});
test('root generation frees a rejected side and refuses empty legal positions', () => {
  for (const side of ['w', 'b']) {
    let freed = 0;
    assert.throws(() => fixedPositions({ fixtures: [{ name: 'bad', side: 'b', record: {} }] }, () => ({ sideToMove: () => side, ply: () => 0, hash: () => 'a'.repeat(16), legalMoves: () => side === 'w' ? ['111211'] : [], free: () => freed++ }), () => 0));
    assert.equal(freed, 1);
  }
});
test('twenty switches exclude the initial load and use only measured working formats', () => {
  assert.deepEqual(switchPrecisions(['fp32', 'fp16', 'int8']).slice(0, 4), ['fp16', 'int8', 'fp32', 'fp16']);
  const steps = switchPrecisions(['fp32', 'int8']); assert.equal(steps.length, 20);
  assert.deepEqual(steps.slice(0, 4), ['int8', 'fp32', 'int8', 'fp32']);
  assert.deepEqual(switchPrecisions(['fp16', 'int8']).slice(0,4), ['int8', 'fp16', 'int8', 'fp16']);
  for (const formats of [[], ['fp32'], ['fp32', 'other']]) assert.throws(() => switchPrecisions(formats));
});
function fake() {
  const workers = []; let tick = 0;
  class Worker {
    constructor(url, options) { assert.equal(url, '/policy.js'); assert.equal(options.type, 'module'); this.messages = [];this.listeners = {};this.closed = false;workers.push(this); }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    postMessage(message) { this.messages.push(message); }
    terminate() { this.closed = true; }
    emit(data) { this.listeners.message({ data }); }
  }
  const scope = { Worker, performance: { now: () => ++tick }, setTimeout, clearTimeout, __trainedFiles: [{ path: 'model/fp32.onnx', file: 'opaque test file' }] };
  const bridge = installPolicyBridge({ workerUrl: '/policy.js', timeoutMs: 1000 }, scope);
  const selection = { modelId: 'model', packageHash: 'a'.repeat(64), precision: 'fp32', backend: 'wasm' };
  return { bridge, selection, scope, workers };
}
test('real bridge sends files once, ignores progress and mismatched IDs, then times the actual reply', async () => {
  const f = fake(); f.bridge.select(f.selection);
  const root = { revision: 7 }, pending = f.bridge.run(root);
  const worker = f.workers[0], request = worker.messages[0];
  assert.equal(request.schema, 1);assert.equal(request.kind, 'policy');assert.equal(request.root.revision, 7);assert.deepEqual(request.files, f.scope.__trainedFiles);
  worker.emit({ kind: 'progress', requestId: request.requestId }); assert.equal(f.bridge.pending, true);
  worker.emit({ kind: 'result', requestId: request.requestId + 1 });assert.equal(f.bridge.pending, true);
  worker.emit({ kind: 'result', requestId: request.requestId, result: { inferenceMs: 3 }, validation: { fixtures: [] } });
  const result = await pending;assert.equal(result.inferenceMs, 3);assert.ok(result.roundTripMs > 0);assert.equal(f.bridge.pending, false);
  const next = f.bridge.run(root);assert.equal(worker.messages[1].files, undefined);assert.equal(worker.messages[1].requestId, request.requestId + 1);
  worker.emit({ kind: 'result', requestId: worker.messages[1].requestId, result: { inferenceMs: 2 } });await next;
  f.bridge.dispose();assert.equal(worker.closed, true);
});
test('format switches terminate the old Worker and resend the same local files to a new one', async () => {
  const f=fake();f.bridge.select(f.selection);const first=f.bridge.run({});
  await assert.rejects(f.bridge.run({}), /busy/);
  f.bridge.select({ ...f.selection, precision: 'int8' });await assert.rejects(first, /cancel/);assert.equal(f.workers[0].closed,true);
  const second=f.bridge.run({});assert.deepEqual(f.workers[1].messages[0].files,f.scope.__trainedFiles);
  f.workers[1].emit({ kind:'result',requestId:f.workers[1].messages[0].requestId,result:{inferenceMs:1} });await second;f.bridge.dispose();
});
test('initialization errors are preserved and do not silently substitute a different backend', async () => {
  const f=fake();f.bridge.select({...f.selection,backend:'webgpu'});const pending=f.bridge.run({});
  f.workers[0].emit({kind:'error',requestId:1,code:'initialization',message:'shader-f16 is not available'});
  await assert.rejects(pending,error=>error.message==='shader-f16 is not available' && error.stage==='initialization');
  assert.equal(f.workers.length,1);f.bridge.dispose();
});
test('measured repetitions run real requests without holding responses and serialize the error stage', async () => {
  const { runPolicyRequests }=await import('../trained-benchmark.mjs');
  let calls=0;const scope={trainedBenchmark:{measuring:false,run:async root=>{assert.equal(root.cursor,1);assert.equal(scope.trainedBenchmark.measuring,calls>=10);return {inferenceMs:++calls};}}};
  const value=await runPolicyRequests({root:{cursor:1},count:40,warmup:10},scope);
  assert.equal(calls,40);assert.equal(value.samples.length,30);assert.equal(value.samples[0].inferenceMs,11);assert.equal(value.samples.at(-1).inferenceMs,40);assert.equal(scope.trainedBenchmark.measuring,false);
  scope.trainedBenchmark.run=async()=>{throw Object.assign(new Error('unsupported'),{stage:'initialization'});};
  assert.deepEqual(await runPolicyRequests({root:{}},scope),{samples:[],error:{stage:'initialization',message:'unsupported'}});
});
test('policy IDs use the fixed canonical coordinates and drop offset, independently calculated', async () => {
  const {canonicalAction}=await import('../trained-benchmark.mjs');
  assert.equal(canonicalAction('111211','b'),2);assert.equal(canonicalAction('111211+','w'),1062879);
  assert.equal(canonicalAction('P*111','b'),1062882);assert.equal(canonicalAction('P*111','w'),1063610);assert.equal(canonicalAction('577567','b'),794222);
});
