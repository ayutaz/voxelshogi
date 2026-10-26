import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const wrapper = fileURLToPath(new URL('./mutation-cargo.sh', import.meta.url));
function run(args, preflightStatus = 0) {
  const directory = mkdtempSync(join(tmpdir(), 'voxelshogi-cargo-gate-'));
  try {
    const cargo = join(directory, 'cargo');
    const log = join(directory, 'calls.jsonl');
    writeFileSync(cargo, `#!/usr/bin/env node
import { appendFileSync } from 'node:fs';
appendFileSync(process.env.TEST_CALLS, JSON.stringify({ args: process.argv.slice(2), cargo: process.env.CARGO }) + '\\n');
if (process.argv.includes('--test') && process.argv.includes('geometry_contracts')) process.exit(Number(process.env.TEST_PREFLIGHT_STATUS));
`, { mode: 0o755 });
    const result = spawnSync(wrapper, args, { encoding: 'utf8', env: { ...process.env,
      CARGO: wrapper, VOXELSHOGI_MUTATION_CARGO: cargo, TEST_CALLS: log,
      TEST_PREFLIGHT_STATUS: String(preflightStatus),
    } });
    const calls = readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse);
    return { result, calls, cargo };
  } finally { rmSync(directory, { recursive: true, force: true }); }
}

test('failed coordinate assertions stop before the expensive test suite', () => {
  const { result, calls } = run(['test', '--package=voxelshogi-core', '--locked'], 101);
  assert.equal(result.status, 101);
  assert.equal(calls.length, 1);
  assert.ok(calls[0].args.includes('geometry_contracts'));
});

test('successful coordinates continue with the full original command and real Cargo', () => {
  const args = ['test', '--verbose', '--package=voxelshogi-core@0.1.0', '--locked'];
  const { result, calls, cargo } = run(args);
  assert.equal(result.status, 0);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1].args, args);
  assert.deepEqual(calls.map(call => call.cargo), [cargo, cargo]);
});

test('build and metadata commands delegate without running a test preflight', () => {
  for (const args of [['test', '--no-run', '--locked'], ['metadata', '--format-version=1']]) {
    const { result, calls } = run(args, 101);
    assert.equal(result.status, 0);
    assert.deepEqual(calls.map(call => call.args), [args]);
  }
});

test('preflight infrastructure errors remain errors, rather than assertion failures', () => {
  const { result, calls } = run(['test', '--locked'], 127);
  assert.equal(result.status, 127);
  assert.equal(calls.length, 1);
});
