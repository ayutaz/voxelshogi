// Pure research input/numerical contract, shared by Node and the real Worker.
const names = ['full', 'axial', 'geometry', 'cnn'];
const sha = (value, length = 64) => typeof value === 'string' && new RegExp(`^[0-9a-f]{${length}}$`).test(value);
function check(condition, message) { if (!condition) throw new Error(message); }
function file(value, bytes) {
  check(value && typeof value.path === 'string' && /^[a-z0-9/._-]+$/.test(value.path) && !value.path.startsWith('/') && !value.path.split('/').some(p => !p || p === '.' || p === '..'), 'unsafe research file path');
  check(Number.isSafeInteger(value.bytes) && value.bytes > 0 && value.bytes <= 512 * 1024 * 1024 && (bytes === undefined || value.bytes === bytes) && sha(value.sha256), 'invalid research file bytes/hash');
}
export function requireLinux(platform) { check(platform === 'linux', 'real research browser execution requires external Linux'); }
export function researchBrowserCases() { return names.flatMap(name => ['wasm', 'webgpu'].map(backend => ({ name, backend }))); }
export function validateBrowserInputs(value) {
  check(value?.schema === 'voxelshogi-research-browser-input-v1' && value.trained === false && sha(value.model_source_commit, 40) && sha(value.release_sha256), 'invalid untrained research origin');
  check(value.origin?.repo_id === 'voxelshogi/voxelshogi-research-operator-probe-v1' && sha(value.origin.revision, 40), 'fixed research Hub revision required');
  check(value.warmup_steps === 8 && value.measured_steps === 32, 'research browser work differs');
  check(JSON.stringify(Object.keys(value.numeric ?? {}).sort()) === JSON.stringify(['policy_atol', 'policy_rtol', 'value_atol', 'value_rtol']) && value.numeric.policy_atol === 1e-4 && value.numeric.policy_rtol === 1e-4 && value.numeric.value_atol === 1e-5 && value.numeric.value_rtol === 1e-5, 'research tolerances differ');
  check(Array.isArray(value.models) && value.models.length === 4 && new Set(value.models.map(m => m.name)).size === 4 && names.every(name => value.models.some(m => m.name === name)), 'all four research architectures required');
  const paths = [];
  for (const model of value.models) {
    check(Number.isSafeInteger(model.parameters) && model.parameters >= 20_000_000 && model.parameters <= 35_000_000, 'actual M parameter range required');
    file(model.model); paths.push(model.model.path);
    check(Array.isArray(model.fixtures) && model.fixtures.length === 2 && model.fixtures[0].id === 0 && model.fixtures[1].id === 3, 'both frozen fixtures required');
    for (const fixture of model.fixtures) {
      file(fixture.features, 729 * 43 * 4);file(fixture.policy, 1067985 * 4);file(fixture.value, 4);
      paths.push(fixture.features.path, fixture.policy.path, fixture.value.path);
      const legal = fixture.legal_actions;
      check(Array.isArray(legal) && legal.length > 0 && legal.every((a, i) => Number.isSafeInteger(a) && a >= 0 && a < 1067985 && (i === 0 || a > legal[i - 1])), 'sorted unique legal actions required');
    }
  }
  check(new Set(paths).size === paths.length, 'repeated research payload paths');
}
export function compareVector(expected, actual, elements, atol, rtol) {
  check(expected instanceof Float32Array && actual instanceof Float32Array && expected.length === elements && actual.length === elements && elements > 0, 'full reference length/dtype differs');
  check(Number.isFinite(atol) && Number.isFinite(rtol) && atol >= 0 && rtol >= 0, 'invalid numeric limits');
  let exceeded = 0, max_abs = 0;
  for (let i = 0; i < elements; i++) {
    check(Number.isFinite(expected[i]) && Number.isFinite(actual[i]), 'nonfinite reference/output');
    const delta = Math.abs(expected[i] - actual[i]);
    if (delta > atol + rtol * Math.abs(expected[i])) exceeded++;
    max_abs = Math.max(max_abs, delta);
  }
  return { elements, exceeded, max_abs };
}
export async function readResearch(url, descriptor, fetcher = fetch) {
  file(descriptor);
  const response = await fetcher(url, { cache: 'no-store' });
  check(response.ok && response.body, 'research download failed');
  const reader = response.body.getReader(), chunks = [];
  let count = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > descriptor.bytes) { await reader.cancel(); throw new Error('research download exceeds declared size'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  check(count === descriptor.bytes, 'research download size differs');
  const bytes = new Uint8Array(count);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset);offset += chunk.byteLength; }
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2, '0')).join('');
  check(digest === descriptor.sha256, 'research download hash differs');
  return bytes;
}
export function validateProvider(row) {
  const provider = row.backend === 'wasm' ? 'CPUExecutionProvider' : 'WebGpuExecutionProvider';
  check(['wasm', 'webgpu'].includes(row.backend) && row.information?.backend === row.backend, 'backend identity differs');
  const entries = Object.entries(row.profile?.providers ?? {}), operators = Object.entries(row.profile?.operators ?? {});
  check(entries.length === 1 && entries[0][0] === provider && Number.isSafeInteger(entries[0][1]) && entries[0][1] > 0 && operators.length > 0 && operators.every(([, n]) => Number.isSafeInteger(n) && n > 0), 'missing or mixed actual execution providers');
  if (row.backend === 'webgpu') {
    const adapter = row.information.adapter, text = adapter && Object.values(adapter).join(' ');
    check(typeof text === 'string' && text.trim().length > 0 && !/swiftshader|llvmpipe|lavapipe|software/i.test(text), 'hardware WebGPU identity unavailable or software fallback');
  }
}
