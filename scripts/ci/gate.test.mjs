import assert from 'node:assert/strict';
import test from 'node:test';
import { checkGate } from './gate.mjs';

const passing = () => Object.fromEntries(['lint', 'rust', 'msrv', 'web', 'audit', 'dependency-review'].map((name) => [name, { result: 'success' }]));

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
  assert.equal(checkGate({}, 'push').length, 6);
});

test('a failed dependency audit blocks the gate', () => {
  const needs = passing();
  needs.audit.result = 'failure';
  assert.deepEqual(checkGate(needs, 'pull_request'), ['audit: failure']);
});

test('dependency review may only be skipped outside pull requests', () => {
  const needs = passing();
  needs['dependency-review'].result = 'skipped';
  assert.deepEqual(checkGate(needs, 'push'), []);
  assert.deepEqual(checkGate(needs, 'workflow_dispatch'), []);
  assert.deepEqual(checkGate(needs, 'pull_request'), ['dependency-review: skipped']);
});

test('invalid input cannot pass', () => {
  assert.throws(() => checkGate(null, 'push'), /needs/);
  assert.throws(() => checkGate([], 'push'), /needs/);
});
