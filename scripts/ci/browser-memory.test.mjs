import assert from 'node:assert/strict';
import test from 'node:test';
import { residentSets } from '../browser-memory.mjs';

test('resident set measurements use only the dedicated browser process IDs and convert KiB to bytes', () => {
  const processes = [{ id: 101, type: 'browser' }, { id: 202, type: 'renderer' }, { id: 303, type: 'GPU' }];
  const report = residentSets(' 101 10240\n 202 5\n', processes);
  assert.deepEqual(report.processes, [{ pid: 101, type: 'browser', rssBytes: 10485760 }, { pid: 202, type: 'renderer', rssBytes: 5120 }]);
  assert.equal(report.totalRssBytes, 10490880);
  assert.deepEqual(report.missingProcessIds, [303]); // a process may exit between CDP and ps
  assert.match(report.scope, /shared/);
  assert.throws(() => residentSets('999 100\n', processes), /unexpected/);
  assert.throws(() => residentSets('101 NaN\n', processes), /invalid/);
  assert.throws(() => residentSets('101 5\n101 5\n', processes), /duplicate/);
});
