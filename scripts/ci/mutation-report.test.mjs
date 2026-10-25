import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { reviewMutations } from './mutation-report.mjs';

const source = 'a reviewed source file';
const mutant = { name: 'src/state.rs:1:1: equivalent change', file: 'src/state.rs' };
const phases = (status = 'Success') => [
  { phase: 'Build', process_status: 'Success' },
  { phase: 'Test', process_status: status },
];
const row = (summary, phase_results = phases()) => ({ scenario: { Mutant: mutant }, summary, phase_results });
const fixture = (outcome) => ({
  cargo_mutants_version: '27.1.0', end_time: '2026-10-25T00:00:00Z', total_mutants: 1,
  outcomes: [{ scenario: 'Baseline', summary: 'Success', phase_results: phases() }, outcome],
});
const review = [{ name: mutant.name, file: mutant.file, source_sha256: createHash('sha256').update(source).digest('hex'), reason: 'proved equivalent' }];
const sources = { [mutant.file]: source };
const check = (report, approved = []) => reviewMutations(report, [mutant], approved, sources);

test('executed failing tests are caught, not unviable', () => {
  assert.deepEqual(check(fixture(row('CaughtMutant', phases({ Failure: 101 })))), { caught: 1, unviable: 0, equivalent: 0, total: 1 });
  assert.equal(check(fixture(row('Unviable', [{ phase: 'Build', process_status: { Failure: 101 } }]))).unviable, 1);
});
test('unknown survivors fail; reviewed equivalents remain separate from caught', () => {
  const report = fixture(row('MissedMutant'));
  assert.throws(() => check(report), /Unreviewed/);
  assert.deepEqual(check(report, review), { caught: 0, unviable: 0, equivalent: 1, total: 1 });
});
test('changed source or mutation identity invalidates equivalence review', () => {
  assert.throws(() => reviewMutations(fixture(row('MissedMutant')), [mutant], review, { [mutant.file]: 'changed source' }), /review/);
  assert.throws(() => check(fixture(row('MissedMutant')), [{ ...review[0], name: 'different mutation' }]), /Unreviewed/);
});
test('timeouts, absent tests and unsupported outcomes cannot pass', () => {
  for (const summary of ['Timeout', 'Success', 'Other']) assert.throws(() => check(fixture(row(summary))), /outcome/);
  assert.throws(() => check(fixture(row('CaughtMutant', [{ phase: 'Build', process_status: 'Success' }]))), /test/);
  assert.throws(() => check(fixture(row('CaughtMutant', phases()))), /test/);
});
test('empty, incomplete and duplicate inventories cannot pass', () => {
  const report = fixture(row('CaughtMutant', phases({ Failure: 101 })));
  assert.throws(() => reviewMutations(report, [], [], {}), /inventory/);
  assert.throws(() => check({ ...report, end_time: null }), /Incomplete/);
  assert.throws(() => check({ ...report, total_mutants: 2 }), /count/);
  assert.throws(() => check({ ...report, outcomes: [report.outcomes[0]] }), /count/);
  assert.throws(() => reviewMutations({ ...report, total_mutants: 2, outcomes: [...report.outcomes, report.outcomes[1]] }, [mutant, mutant], [], {}), /Duplicate/);
});
test('failed or missing baseline and changed tool versions cannot pass', () => {
  const report = fixture(row('CaughtMutant', phases({ Failure: 101 })));
  assert.throws(() => check({ ...report, outcomes: report.outcomes.slice(1) }), /baseline/);
  assert.throws(() => check({ ...report, outcomes: [{ scenario: 'Baseline', summary: 'Success', phase_results: phases({ Failure: 101 }) }, report.outcomes[1]] }), /baseline/);
  assert.throws(() => check({ ...report, cargo_mutants_version: 'different' }), /version/);
});
