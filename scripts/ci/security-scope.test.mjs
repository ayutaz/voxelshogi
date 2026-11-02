import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { codeqlRequired } from './security-scope.mjs';
import { verificationScope } from './ci-scope.mjs';

const keys = ['rust', 'web', 'python', 'models', 'dependencies', 'controls', 'deep'];
const scope = (event = 'pull_request', files = ['README.md']) => ({
  result: 'success',
  outputs: Object.fromEntries(Object.entries(verificationScope(files, event)).map(([key, value]) => [key, String(value)])),
});

test('only proven documentation-only PR and main comparisons omit CodeQL analysis', () => {
  for (const event of ['pull_request', 'push']) {
    assert.equal(codeqlRequired(scope(event), event), false);
    assert.equal(codeqlRequired(scope(event, ['docs/ROADMAP.md', 'CONTRIBUTING.md']), event), false);
    for (const files of [null, [], ['unknown/input'], ['crates/core/lib.rs'], ['training/model.py'], ['apps/web/src/App.tsx'], ['.github/workflows/security.yml'], ['docs/generated.json'], ['training/old.py', 'docs/new.md']]) {
      assert.equal(codeqlRequired(scope(event, files), event), true, `${event}: ${JSON.stringify(files)}`);
    }
  }
});

test('any affected impact category keeps all four language analyses', () => {
  for (const key of keys.filter(key => key !== 'deep')) {
    const value = scope(); value.outputs[key] = 'true';
    assert.equal(codeqlRequired(value, 'pull_request'), true, key);
  }
});

test('scheduled, manual and unknown events always analyze even with valid empty impact', () => {
  for (const event of ['schedule', 'workflow_dispatch', 'unknown', undefined]) {
    assert.equal(codeqlRequired(scope('push'), event), true, String(event));
  }
});

test('failed, skipped, cancelled or absent scope cannot authorize a successful CodeQL check', () => {
  for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
    assert.throws(() => codeqlRequired({ ...scope(), result }, 'pull_request'), /scope must succeed/);
  }
  for (const value of [undefined, null, {}]) assert.throws(() => codeqlRequired(value, 'pull_request'), /scope must succeed/);
});

test('every scope flag is required and must be a literal boolean string', () => {
  for (const key of keys) {
    for (const invalid of [undefined, true, false, '', 'FALSE', 'unknown', 0]) {
      const value = scope(); value.outputs[key] = invalid;
      assert.throws(() => codeqlRequired(value, 'pull_request'), /invalid outputs/, `${key}: ${invalid}`);
    }
    const value = scope(); delete value.outputs[key];
    assert.throws(() => codeqlRequired(value, 'pull_request'), /invalid outputs/, key);
  }
  assert.throws(() => codeqlRequired({ result: 'success' }, 'pull_request'), /invalid outputs/);
  assert.throws(() => codeqlRequired(scope(), 'push'), /deep verification/);
});

test('workflow keeps required names and executes typed proof before both expensive CodeQL steps', () => {
  const workflow = readFileSync(new URL('../../.github/workflows/security.yml', import.meta.url), 'utf8');
  assert.match(workflow, /scope:\n\s+uses: \.\/\.github\/workflows\/change-scope\.yml/);
  assert.match(workflow, /codeql:\n\s+name: CodeQL \(\$\{\{ matrix.language \}\}\)\n\s+needs: scope\n\s+if: always\(\)/);
  assert.match(workflow, /language: \[rust, javascript-typescript, actions, python\]/);
  assert.match(workflow, /- id: proof\n\s+env:\n\s+SCOPE_JSON: \$\{\{ toJSON\(needs.scope\) \}\}\n\s+run: node scripts\/ci\/security-scope.mjs/);
  for (const action of ['init', 'analyze']) {
    assert.match(workflow, new RegExp('- if: steps.proof.outputs.analyze == \'true\'\\n\\s+uses: github/codeql-action/' + action + '@'));
  }
});

test('CLI emits typed analysis output only after validating scope', async () => {
  const { mkdtempSync, writeFileSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { spawnSync } = await import('node:child_process');
  const root = mkdtempSync(join(tmpdir(), 'voxelshogi-security-scope-'));
  const output = join(root, 'output'), summary = join(root, 'summary');
  try {
    for (const [event, files, expected] of [['pull_request', ['README.md'], 'false'], ['push', ['docs/ROADMAP.md'], 'false'], ['pull_request', null, 'true'], ['schedule', null, 'true']]) {
      writeFileSync(output, ''); writeFileSync(summary, '');
      const result = spawnSync(process.execPath, [new URL('./security-scope.mjs', import.meta.url).pathname], {
        encoding: 'utf8', env: { ...process.env, GITHUB_EVENT_NAME: event, SCOPE_JSON: JSON.stringify(scope(event, files)), GITHUB_OUTPUT: output, GITHUB_STEP_SUMMARY: summary },
      });
      assert.equal(result.status, 0, result.stderr);
      assert.equal(readFileSync(output, 'utf8'), `analyze=${expected}\n`);
    }
    writeFileSync(output, '');
    const invalid = scope(); delete invalid.outputs.rust;
    const result = spawnSync(process.execPath, [new URL('./security-scope.mjs', import.meta.url).pathname], {
      encoding: 'utf8', env: { ...process.env, GITHUB_EVENT_NAME: 'pull_request', SCOPE_JSON: JSON.stringify(invalid), GITHUB_OUTPUT: output, GITHUB_STEP_SUMMARY: summary },
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /invalid outputs/);
    assert.equal(readFileSync(output, 'utf8'), '');
  } finally { rmSync(root, { recursive: true, force: true }); }
});
