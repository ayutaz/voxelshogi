import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyVitest } from './mutation-web.mjs';

test('web mutations require an executed failing assertion, not a build/import failure', () => {
  const report = { numFailedTests: 1, numPassedTests: 0, testResults: [{ assertionResults: [{ status: 'failed' }] }] };
  assert.equal(classifyVitest({ status: 1 }, report), 'caught');
  assert.equal(classifyVitest({ status: 1 }, { ...report, testResults: [] }), 'error');
  assert.equal(classifyVitest({ status: 1 }, { ...report, numFailedTests: 0 }), 'error');
  assert.equal(classifyVitest({ status: 1 }, null), 'error');
  assert.equal(classifyVitest({ status: 1, error: new Error('timeout') }, report), 'error');
  assert.equal(classifyVitest({ status: 1, signal: 'SIGTERM' }, report), 'error');
  assert.equal(classifyVitest({ status: 1 }, { ...report, testResults: [{ assertionResults: [{ status: 'failed', failureMessages: ['Error: Test timed out in 5000ms'] }] }] }), 'error');
});

test('web mutation baseline must have passing tests and no failures', () => {
  const report = { numFailedTests: 0, numPassedTests: 1, testResults: [{ assertionResults: [{ status: 'passed' }] }] };
  assert.equal(classifyVitest({ status: 0 }, report), 'passed');
  assert.equal(classifyVitest({ status: 0 }, { numFailedTests: 0, numPassedTests: 0 }), 'error');
  assert.equal(classifyVitest({ status: 0 }, { ...report, numFailedTests: 1 }), 'error');
  assert.equal(classifyVitest({ status: 1 }, report), 'error');
});
