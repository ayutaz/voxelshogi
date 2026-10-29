/** Metadata/driver helpers; importing this module never executes an engine or model. */
export function fixedPositions(manifest, makeGame, actionIndex) {
  return manifest.fixtures.map(fixture => {
    const recordJson = JSON.stringify(fixture.record), game = makeGame(recordJson);
    try {
      if (game.sideToMove() !== fixture.side) throw new Error('fixture side differs from replay');
      const moves = game.legalMoves();
      if (moves.length === 0) throw new Error('fixed position has no legal moves');
      return { name: fixture.name, root: { revision: 0, cursor: game.ply(), side: fixture.side, hash: game.hash(), ruleset: 'voxelshogi-standard-v1', recordJson },
        legal: moves.map(move => ({ move, action: actionIndex(move, fixture.side) })) };
    } finally { game.free(); }
  });
}
export function switchPrecisions(available) {
  const formats = ['fp32', 'fp16', 'int8'].filter(p => available.includes(p));
  if (formats.length < 2 || formats.length !== available.length) throw new Error('switches require two measured formats');
  return Array.from({ length: 20 }, (_, i) => formats[(i + 1) % formats.length]);
}

/** Warmup is not an interaction measurement. Race completion to avoid hanging on failed requests. */
export async function duringMeasuredRequests(repeating, waitForMeasured, interact) {
  let done = false;
  const completion = repeating.finally(() => { done = true; });
  const measured = await Promise.race([completion.then(() => false), waitForMeasured().then(() => true)]);
  if (measured) for (let attempt = 0; attempt < 20 && !done; attempt++) await interact();
  return completion;
}

/** Serialized directly into the real page by Playwright, also tested with opaque fake Worker ports. */
export function installPolicyBridge({ workerUrl, timeoutMs = 120000 }, scope = globalThis) {
  let worker = null, selected = null, sentFiles = false, next = 0, active = null;
  const bridge = { pending: false, measuring: false, select, run, dispose };
  function dispose() {
    worker?.terminate(); worker = null; sentFiles = false;
    if (active) { scope.clearTimeout(active.timer);active.reject(new Error('policy request cancelled'));active = null; }
    bridge.pending = false;
  }
  function select(value) {
    dispose(); selected = { ...value };worker = new scope.Worker(workerUrl, { type: 'module' });
    worker.addEventListener('message', ({ data }) => {
      if (!active || data.requestId !== active.id || data.kind === 'progress') return;
      const item = active; active = null; scope.clearTimeout(item.timer);bridge.pending = false;
      if (data.kind === 'error') { const error = new Error(data.message);error.stage = data.code;item.reject(error); }
      else if (data.kind !== 'result') item.reject(new Error('unexpected policy response'));
      else item.resolve({ ...data.result, validation: data.validation, roundTripMs: scope.performance.now() - item.started });
    });
    worker.addEventListener('error', event => {
      if (active) { const item = active;active = null;scope.clearTimeout(item.timer);bridge.pending = false;item.reject(new Error(event.message || 'policy Worker failed')); }
    });
  }
  async function run(root) {
    if (active) throw new Error('policy benchmark busy');
    if (!worker || !selected) throw new Error('select a policy model first');
    const id = ++next, request = { schema: 1, kind: 'policy', requestId: id, selection: selected, root,
      ...(!sentFiles ? { files: scope.__trainedFiles } : {}) };
    sentFiles = true;
    return new Promise((resolve, reject) => {
      const timer = scope.setTimeout(() => { active = null;bridge.pending = false;reject(new Error('policy response timed out')); }, timeoutMs);
      active = { id, resolve, reject, timer, started: scope.performance.now() };bridge.pending = true;
      try { worker.postMessage(request); } catch (error) { scope.clearTimeout(timer);active = null;bridge.pending = false;reject(error); }
    });
  }
  scope.trainedBenchmark = bridge;
  return bridge;
}

/** Serialize failures explicitly: browser automation drops custom Error fields. */
export async function runPolicyRequests({ root, count = 1, warmup = 0 }, scope = globalThis) {
  const samples = [];scope.trainedBenchmark.measuring = false;
  try {
    for (let i=0;i<count;i++) {scope.trainedBenchmark.measuring=count>1 && i>=warmup;const result=await scope.trainedBenchmark.run(root);if(i>=warmup)samples.push(result);}
    return { samples };
  } catch(error) { return { samples, error:{stage:error.stage ?? 'measurement',message:String(error.message ?? error)} }; }
  finally {scope.trainedBenchmark.measuring=false;}
}

export function canonicalAction(text, side) {
  const square = chars => { const [x,y,z] = [...chars].map(c => Number(c)-1);const index=z*81+y*9+x;return side==='b'?index:728-index; };
  return text[1]==='*' ? 1062882+'PLNSGBR'.indexOf(text[0])*729+square(text.slice(2)) : 2*(square(text.slice(0,3))*729+square(text.slice(3,6)))+Number(text.endsWith('+'));
}
