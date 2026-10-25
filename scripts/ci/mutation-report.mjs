import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const testPhase = (row) => row.phase_results?.find((phase) => phase.phase === 'Test');
const buildPhase = (row) => row.phase_results?.find((phase) => phase.phase === 'Build');

export function reviewMutations(report, inventory, approved, sources) {
  assert.equal(report.cargo_mutants_version, '27.1.0', 'Unsupported cargo-mutants version');
  assert.ok(report.end_time, 'Incomplete mutation report');
  assert.ok(Array.isArray(inventory) && inventory.length > 0, 'Empty mutation inventory');
  const expected = new Map(inventory.map((mutant) => [mutant.name, mutant]));
  assert.equal(expected.size, inventory.length, 'Duplicate mutation inventory');
  const baselines = report.outcomes.filter((row) => row.scenario === 'Baseline');
  assert.equal(baselines.length, 1, 'Missing or duplicate baseline');
  assert.ok(baselines[0].summary === 'Success' && buildPhase(baselines[0])?.process_status === 'Success'
    && testPhase(baselines[0])?.process_status === 'Success', 'Unsuccessful baseline');
  const rows = report.outcomes.filter((row) => row.scenario !== 'Baseline');
  assert.equal(rows.length, inventory.length, 'Mutation outcome count mismatch');
  assert.equal(report.total_mutants, rows.length, 'Mutation total count mismatch');
  const counts = { caught: 0, unviable: 0, equivalent: 0, total: rows.length };
  const seen = new Set();
  for (const row of rows) {
    const mutant = row.scenario?.Mutant;
    assert.ok(mutant && expected.has(mutant.name), 'Unknown mutation in outcome');
    assert.equal(mutant.file, expected.get(mutant.name).file, 'Mutation file mismatch');
    assert.ok(!seen.has(mutant.name), 'Duplicate mutation outcome');
    seen.add(mutant.name);
    if (row.summary === 'CaughtMutant') {
      assert.ok(buildPhase(row)?.process_status === 'Success' && testPhase(row)?.process_status?.Failure === 101,
        'Caught mutation must have executed failing tests');
      counts.caught++;
    } else if (row.summary === 'Unviable') {
      assert.ok(buildPhase(row)?.process_status?.Failure === 101 && !testPhase(row), 'Invalid unviable outcome');
      counts.unviable++;
    } else if (row.summary === 'MissedMutant') {
      assert.ok(buildPhase(row)?.process_status === 'Success' && testPhase(row)?.process_status === 'Success', 'Invalid surviving test outcome');
      const entry = approved.find((item) => item.name === mutant.name && item.file === mutant.file);
      assert.ok(entry, `Unreviewed surviving mutation: ${mutant.name}`);
      assert.ok(typeof entry.reason === 'string' && entry.reason.trim(), 'Missing equivalence review reason');
      assert.ok(typeof sources[entry.file] === 'string', 'Missing reviewed source');
      assert.equal(createHash('sha256').update(sources[entry.file]).digest('hex'), entry.source_sha256,
        `Source changed; equivalence review required: ${mutant.name}`);
      counts.equivalent++;
    } else {
      throw new Error(`Unsupported mutation outcome: ${row.summary}`);
    }
  }
  return counts;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const directory = resolve(process.argv[2] ?? 'mutants.out');
  const read = (path) => JSON.parse(readFileSync(path, 'utf8'));
  const approved = read(resolve(root, 'scripts/ci/equivalent-mutations.json'));
  const sources = Object.fromEntries(approved.map((entry) => [entry.file, readFileSync(resolve(root, entry.file), 'utf8')]));
  const counts = reviewMutations(read(resolve(directory, 'outcomes.json')), read(resolve(directory, 'mutants.json')), approved, sources);
  writeFileSync(resolve(directory, 'review.json'), JSON.stringify(counts, null, 2) + '\n');
  console.log(JSON.stringify(counts));
}
