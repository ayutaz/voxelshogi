import assert from 'node:assert/strict';
import test from 'node:test';
import { testOutcome } from './mutation-smoke.mjs';

test('only executed, failing tests count as caught mutations', () => {
  const failed = { status: 101, stdout: 'running 1 test\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;', stderr: '' };
  assert.equal(testOutcome(failed), 'caught');
  assert.equal(testOutcome({ ...failed, status: 0 }), 'error');
  assert.equal(testOutcome({ status: 101, stdout: '', stderr: 'error: could not compile' }), 'error');
  assert.equal(testOutcome({ ...failed, error: new Error('timeout'), signal: 'SIGTERM' }), 'error');
});

test('zero tests and survivors cannot be reported as caught', () => {
  assert.equal(testOutcome({ status: 0, stdout: 'running 0 tests\ntest result: ok. 0 passed; 0 failed;', stderr: '' }), 'error');
  assert.equal(testOutcome({ status: 0, stdout: 'running 1 test\ntest result: ok. 1 passed; 0 failed;', stderr: '' }), 'passed');
});
