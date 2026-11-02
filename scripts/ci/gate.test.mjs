import assert from 'node:assert/strict';
import test from 'node:test';
import { checkGate } from './gate.mjs';

const scopeKeys = ['rust', 'web', 'python', 'models', 'dependencies', 'controls', 'deep'];
const passing = () => ({
  ...Object.fromEntries(['scope', 'lint', 'rust', 'msrv', 'web', 'e2e-runtime', 'audit', 'dependency-review', 'python', 'models', 'python-model-mutations', 'python-training-mutations', 'quality'].map((name) => [name, { result: 'success' }])),
  scope: { result: 'success', outputs: Object.fromEntries(scopeKeys.map(name => [name, 'true'])) },
});

test('all required checks must succeed', () => {
  assert.deepEqual(checkGate(passing(), 'pull_request'), []);
});

for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
  test(`a required check cannot be ${result}`, () => {
    const needs = passing();
    needs.web.result = result;
    assert.deepEqual(checkGate(needs, 'pull_request'), [`web: ${result ?? 'missing result'}`]);
  });
}

test('missing and empty results cannot pass', () => {
  const needs = passing();
  delete needs.rust;
  assert.deepEqual(checkGate(needs, 'push'), ['rust: missing result']);
  assert.equal(checkGate({}, 'push').length, 13);
});

test('public E2E runtime handoff must exist and succeed before deployment', () => {
  for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
    const needs = passing();
    needs['e2e-runtime'].result = result;
    assert.deepEqual(checkGate(needs, 'pull_request'), [`e2e-runtime: ${result ?? 'missing result'}`]);
  }
  const needs = passing();
  delete needs['e2e-runtime'];
  assert.deepEqual(checkGate(needs, 'push'), ['e2e-runtime: missing result']);
});

test('a failed dependency audit blocks the gate', () => {
  const needs = passing();
  needs.audit.result = 'failure';
  assert.deepEqual(checkGate(needs, 'pull_request'), ['audit: failure']);
});

test('Python model contracts cannot be failed, skipped, cancelled or missing', () => {
  for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
    const needs = passing();
    needs.python.result = result;
    assert.deepEqual(checkGate(needs, 'pull_request'), [`python: ${result ?? 'missing result'}`]);
  }
  const needs = passing();
  delete needs.python;
  assert.deepEqual(checkGate(needs, 'push'), ['python: missing result']);
});

test('dependency review may only be skipped outside pull requests', () => {
  const needs = passing();
  needs['dependency-review'].result = 'skipped';
  assert.deepEqual(checkGate(needs, 'push'), []);
  assert.deepEqual(checkGate(needs, 'workflow_dispatch'), []);
  assert.deepEqual(checkGate(needs, 'pull_request'), ['dependency-review: skipped']);
});

test('real browser model inference must succeed, including on ordinary PRs', () => {
  for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
    const needs = passing(); needs.models.result = result;
    assert.deepEqual(checkGate(needs, 'pull_request'), [`models: ${result ?? 'missing result'}`]);
  }
  const needs = passing(); delete needs.models;
  assert.deepEqual(checkGate(needs, 'push'), ['models: missing result']);
});

test('invalid input cannot pass', () => {
  assert.throws(() => checkGate(null, 'push'), /needs/);
  assert.throws(() => checkGate([], 'push'), /needs/);
});


test('each mutation matrix must succeed when Python is affected', () => {
  for (const name of ['python-model-mutations', 'python-training-mutations']) {
    for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
      const needs = passing(); needs[name].result = result;
      assert.deepEqual(checkGate(needs, 'pull_request'), [`${name}: ${result ?? 'missing result'}`]);
    }
    const needs = passing(); delete needs[name];
    assert.deepEqual(checkGate(needs, 'push'), [`${name}: missing result`]);
  }
});

test('unaffected Python permits only skipped mutation matrices, not failures or missing jobs', () => {
  const base = passing(); base.scope.outputs.python = 'false';
  base['python-model-mutations'].result = 'skipped';
  base['python-training-mutations'].result = 'skipped';
  assert.deepEqual(checkGate(base, 'pull_request'), []);
  for (const name of ['python-model-mutations', 'python-training-mutations']) {
    for (const result of ['failure', 'cancelled', undefined]) {
      const needs = structuredClone(base); needs[name].result = result;
      assert.deepEqual(checkGate(needs, 'pull_request'), [`${name}: ${result ?? 'missing result'}`]);
    }
  }
  base.python.result = 'skipped';
  assert.deepEqual(checkGate(base, 'pull_request'), ['python: skipped']);
});

test('dependency jobs may skip on PR only with validated dependencies=false', () => {
  const needs = passing(); needs.scope.outputs.dependencies = 'false';
  needs.audit.result = 'skipped'; needs['dependency-review'].result = 'skipped';
  assert.deepEqual(checkGate(needs, 'pull_request'), []);
  for (const name of ['audit', 'dependency-review']) {
    for (const result of ['failure', 'cancelled', undefined]) {
      const bad = structuredClone(needs); bad[name].result = result;
      assert.deepEqual(checkGate(bad, 'pull_request'), [`${name}: ${result ?? 'missing result'}`]);
    }
  }
  needs.scope.outputs.dependencies = 'true';
  assert.deepEqual(checkGate(needs, 'pull_request'), ['audit: skipped', 'dependency-review: skipped']);
});

test('scope must succeed and every output must be a literal true/false string', () => {
  for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
    const needs = passing(); needs.scope.result = result;
    assert.deepEqual(checkGate(needs, 'pull_request'), [`scope: ${result ?? 'missing result'}`]);
  }
  for (const key of scopeKeys) {
    for (const value of [undefined, false, true, '', 'FALSE', 'unknown']) {
      const needs = passing(); needs.scope.outputs[key] = value;
      assert.deepEqual(checkGate(needs, 'pull_request'), ['scope: invalid outputs']);
    }
  }
  const needs = passing(); delete needs.scope.outputs;
  assert.deepEqual(checkGate(needs, 'pull_request'), ['scope: invalid outputs']);
});

test('invalid scope cannot authorize skipped jobs', () => {
  const needs = passing(); needs.scope.outputs.python = 'false';
  delete needs.scope.outputs.rust;
  needs['python-training-mutations'].result = 'skipped';
  assert.deepEqual(checkGate(needs, 'pull_request'), ['scope: invalid outputs', 'python-training-mutations: skipped']);
});


test('PR fast checks may omit deep quality and Python mutation matrices only', () => {
  const needs = passing(); needs.scope.outputs.deep = 'false';
  needs.quality.result = 'skipped';
  needs['python-model-mutations'].result = 'skipped';
  needs['python-training-mutations'].result = 'skipped';
  assert.deepEqual(checkGate(needs, 'pull_request'), []);
  for (const name of ['quality', 'python-model-mutations', 'python-training-mutations']) {
    for (const result of ['failure', 'cancelled', undefined]) {
      const bad = structuredClone(needs); bad[name].result = result;
      assert.deepEqual(checkGate(bad, 'pull_request'), [name + ': ' + (result ?? 'missing result')]);
    }
    const bad = structuredClone(needs); delete bad[name];
    assert.deepEqual(checkGate(bad, 'pull_request'), [name + ': missing result']);
  }
  for (const name of ['msrv', 'models', 'web']) {
    const bad = structuredClone(needs); bad[name].result = 'skipped';
    assert.deepEqual(checkGate(bad, 'pull_request'), [name + ': skipped']);
  }
});

test('main, periodic and manual runs require successful deep quality', () => {
  for (const event of ['push', 'schedule', 'workflow_dispatch', 'unknown']) {
    for (const result of ['failure', 'cancelled', 'skipped', undefined]) {
      const needs = passing(); needs.quality.result = result;
      assert.deepEqual(checkGate(needs, event), ['quality: ' + (result ?? 'missing result')]);
    }
    const needs = passing(); delete needs.quality;
    assert.deepEqual(checkGate(needs, event), ['quality: missing result']);
  }
});

test('deep=false outside PR cannot authorize missing heavy verification', () => {
  for (const event of ['push', 'schedule', 'workflow_dispatch', 'unknown']) {
    const needs = passing(); needs.scope.outputs.deep = 'false';
    needs.quality.result = 'skipped';
    assert.deepEqual(checkGate(needs, event), ['scope: invalid outputs', 'quality: skipped']);
  }
});
