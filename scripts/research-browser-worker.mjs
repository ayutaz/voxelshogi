// Development-only Worker, served on loopback by the Linux measurement runner.
import { openBackend } from '../apps/web/src/inference/backend.ts';
import { compareVector, readResearch, validateBrowserInputs } from './research-browser-contract.mjs';

self.onmessage = async ({ data }) => {
  let port, session, stage = 'input';
  try {
    validateBrowserInputs(data.plan);
    const model = data.plan.models.find(m => m.name === data.name);
    if (!model || !['wasm', 'webgpu'].includes(data.backend)) throw new Error('unknown research case');
    const base = data.runtime.assetBase;
    stage = 'runtime';
    port = await openBackend(data.runtime, data.backend, 'fp32');
    stage = 'model';
    const bytes = await readResearch(new URL(model.model.path, base).href, model.model);
    const begin = performance.now();
    session = await port.createSession(bytes, 'fp32');
    const init_ms = performance.now() - begin, fixtures = [];
    for (const fixture of model.fixtures) {
      stage = `fixture${fixture.id}`;
      const refs = await Promise.all([fixture.features, fixture.policy, fixture.value].map(f => readResearch(new URL(f.path, base).href, f)));
      const [features, policy, value] = refs.map(b => new Float32Array(b.buffer, b.byteOffset, b.byteLength / 4));
      if (features.length !== 729 * 43 || features.some(x => !Number.isFinite(x))) throw new Error('invalid frozen features');
      const times = [], comparisons = { policy: null, value: null };
      for (let i = 0; i < data.plan.warmup_steps + data.plan.measured_steps; i++) {
        const tick = performance.now();
        const outputs = await session.run(features);
        const elapsed = performance.now() - tick;
        try {
          const numeric = data.plan.numeric;
          const current = {
            policy: compareVector(policy, outputs.policy, 1067985, numeric.policy_atol, numeric.policy_rtol),
            value: compareVector(value, outputs.value, 1, numeric.value_atol, numeric.value_rtol),
          };
          const best = vector => fixture.legal_actions.reduce((a, b) => vector[b] > vector[a] ? b : a);
          if (current.policy.exceeded || current.value.exceeded || best(policy) !== best(outputs.policy)) throw new Error('research full-vector tolerance or legal argmax differs');
          for (const name of ['policy', 'value']) {
            current[name].max_abs = Math.max(current[name].max_abs, comparisons[name]?.max_abs ?? 0);
            comparisons[name] = current[name];
          }
          if (i >= data.plan.warmup_steps) times.push(elapsed);
        } finally { outputs.dispose(); }
      }
      fixtures.push({ id: fixture.id, comparisons, legal_argmax_equal: true, warmup_steps: data.plan.warmup_steps, samples_ms: times });
    }
    stage = 'release';
    await session.finishProfiling?.();
    await session.release(); session = null;
    const information = port.info, profile = port.profile(), buffers = port.buffers?.() ?? null;
    await port.dispose(); port = null;
    self.postMessage({ status: 'success', name: data.name, backend: data.backend, init_ms, fixtures, information, profile, buffers, session_released: true });
  } catch (error) {
    self.postMessage({ status: 'failed', name: data.name, backend: data.backend, stage, error_type: error.name, error_message: String(error.message).slice(0, 1024) });
  } finally {
    try { await session?.release(); } finally { await port?.dispose(); }
  }
};
