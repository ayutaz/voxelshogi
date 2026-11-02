import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyChanges } from './ci-scope.mjs';

const none = { rust: false, web: false, python: false, models: false, dependencies: false, controls: false };
const all = Object.fromEntries(Object.keys(none).map(k => [k, true]));
test('planning and README changes do not rebuild code', () => {
  assert.deepEqual(classifyChanges(['README.md', 'CLAUDE.md', 'docs/ROADMAP.md']), none);
});
test('unknown paths and shared CI/dependencies fail closed to full checks', () => {
  for (const file of ['new-package/file.xyz', '.github/workflows/ci.yml', 'scripts/ci/ci-scope.mjs', 'uv.lock', 'Cargo.lock', 'apps/web/pnpm-lock.yaml'])
    assert.deepEqual(classifyChanges([file]), all, file);
  assert.deepEqual(classifyChanges([]), all);
});
test('training changes run Python and model verification without unrelated Web or Rust builds', () => {
  assert.deepEqual(classifyChanges(['training/selfplay_training.py']), { ...none, python: true, models: true });
});
test('shared Rust boundaries reach Python, WASM and browser models', () => {
  assert.deepEqual(classifyChanges(['crates/voxelshogi-core/src/lib.rs']), { ...none, rust: true, web: true, python: true, models: true });
});
test('UI changes run Web and real browser model interactions', () => {
  assert.deepEqual(classifyChanges(['apps/web/src/App.tsx']), { ...none, web: true, models: true });
});
test('union keeps every impact, including deletions on either side of a rename', () => {
  assert.deepEqual(classifyChanges(['docs/README.md','training/old.py','apps/web/src/new.ts']), { ...none, web: true, python: true, models: true });
});

test('manual, schedule, missing history and initial pushes require full verification', async () => {
  const { changedFiles } = await import('./ci-scope.mjs');
  for (const name of ['schedule','workflow_dispatch','push']) assert.equal(changedFiles(name, {}), null);
  assert.equal(changedFiles('push', {before:'0'.repeat(40)}), null);
  assert.equal(changedFiles('push', {before:'a'.repeat(40)}, () => { throw new Error('missing base'); }), null);
  let args;
  assert.deepEqual(changedFiles('pull_request', {pull_request:{base:{sha:'a'.repeat(40)}}}, (binary, value) => { args=[binary,...value]; return 'training/old.py\0docs/new.md\0'; }), ['training/old.py','docs/new.md']);
  assert.deepEqual(args, ['git','diff','--name-only','--no-renames','-z','a'.repeat(40),'HEAD']);
});

test('renaming a code file into documentation keeps its executable impact', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, renameSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { execFileSync } = await import('node:child_process');
  const { changedFiles } = await import('./ci-scope.mjs');
  const root = mkdtempSync(join(tmpdir(), 'voxelshogi-scope-'));
  const git = args => execFileSync('git', args, {cwd:root, encoding:'utf8'}).trim();
  try {
    git(['init','--quiet','--initial-branch=scope-test']);
    mkdirSync(join(root,'crates/core'),{recursive:true}); writeFileSync(join(root,'crates/core/lib.rs'),'// fixture\n');
    git(['add','.']); git(['-c','user.name=CI Scope','-c','user.email=ci@voxelshogi.invalid','commit','--quiet','-m','baseline']);
    const base = git(['rev-parse','HEAD']); mkdirSync(join(root,'docs')); renameSync(join(root,'crates/core/lib.rs'),join(root,'docs/example.md'));
    git(['add','.']); git(['-c','user.name=CI Scope','-c','user.email=ci@voxelshogi.invalid','commit','--quiet','-m','rename']);
    const paths = changedFiles('push', {before:base}, (binary,args,options) => execFileSync(binary,args,{...options,cwd:root}));
    assert.deepEqual(paths,['crates/core/lib.rs','docs/example.md']);
    assert.equal(classifyChanges(paths).rust,true);
    assert.equal(classifyChanges(paths).python,true);
  } finally { rmSync(root,{recursive:true,force:true}); }
});


test('PRs defer deep checks even for unknown paths; every other event keeps deep verification', async () => {
  const { verificationScope } = await import('./ci-scope.mjs');
  assert.deepEqual(verificationScope(['unknown/new.input'], 'pull_request'), {...all, deep:false});
  assert.deepEqual(verificationScope(null, 'pull_request'), {...all, deep:false});
  assert.deepEqual(verificationScope(['README.md'], 'pull_request'), {...none, deep:false});
  for (const event of ['push','schedule','workflow_dispatch','unknown',undefined]) {
    assert.deepEqual(verificationScope(null, event), {...all, deep:true});
  }
  assert.deepEqual(verificationScope(['README.md'], 'push'), {...none, deep:true});
});
