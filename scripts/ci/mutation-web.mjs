import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export function classifyVitest(processResult, report) {
  if (processResult.error || processResult.signal || !report) return 'error';
  const assertions = (report.testResults ?? []).flatMap((suite) => suite.assertionResults ?? []);
  if (assertions.some((a) => (a.failureMessages ?? []).some((message) => /(?:test|hook) timed out|exceeded timeout|timeout - async callback/i.test(message)))) return 'error';
  if (processResult.status === 0 && report.numFailedTests === 0 && report.numPassedTests > 0 && assertions.some((a) => a.status === 'passed')) return 'passed';
  if (processResult.status === 1 && report.numFailedTests > 0 && assertions.some((a) => a.status === 'failed')) return 'caught';
  return 'error';
}

const mutations = [
  { name: 'worker-port-origin', file: 'ai/search.worker.ts', before: "if (event.origin !== '') return;", after: '', test: 'search-worker' },
  { name: 'worker-terminate', file: 'ai/search-client.ts', before: 'w.terminate();', after: '', test: 'search-client' },
  { name: 'worker-stale-callback', file: 'ai/search-client.ts', before: 'this.worker !== worker || !this.pending', after: '!this.pending', test: 'search-client' },
  { name: 'worker-stale-error', file: 'ai/search-client.ts', before: 'if (this.worker === worker) this.fail(new Error(event.message', after: 'if (true) this.fail(new Error(event.message', test: 'search-client' },
  { name: 'worker-duplicate-id', file: 'ai/search-client.ts', before: 'data.requestId !== p.request.requestId', after: 'false', test: 'search-client' },
  { name: 'worker-invalid-id', file: 'ai/search-client.ts', before: 'Number.isSafeInteger(data.requestId) && data.requestId > 0 && ', after: '', test: 'search-client' },
  { name: 'worker-busy', file: 'ai/search-client.ts', before: "if (this.pending) return Promise.reject(new Error('search client busy'));", after: '', test: 'search-client' },
  { name: 'worker-root-revision', file: 'ai/search-protocol.ts', before: "['schema', 'requestId', 'revision', 'ruleset', 'cursor', 'hash', 'side', 'difficulty'] as const", after: "['schema', 'requestId', 'ruleset', 'cursor', 'hash', 'side', 'difficulty'] as const", test: 'search-client' },
  { name: 'worker-random-fallback', file: 'ai/search-protocol.ts', before: "r.stopReason !== 'random' || request.difficulty === 'easy'", after: 'true', test: 'search-protocol' },
  { name: 'worker-node-precision', file: 'ai/search-protocol.ts', before: "BigInt(n) <= 18_446_744_073_709_551_615n", after: 'true', test: 'search-protocol' },
  { name: 'worker-record-bytes', file: 'ai/search-protocol.ts', before: 'new TextEncoder().encode(r.recordJson).length <= 4 * 1024 * 1024', after: 'true', test: 'search-protocol' },
  { name: 'worker-cursor', file: 'ai/search-engine.ts', before: 'game.goto(request.cursor);', after: 'game.goto(game.moveCount());', test: 'search-engine' },
  { name: 'worker-history', file: 'ai/search-engine.ts', before: 'Game.fromRecordJson(request.recordJson)', after: 'Game.fromVsfen(JSON.parse(request.recordJson).initial)', test: 'search-engine' },
  { name: 'worker-game-free', file: 'ai/search-engine.ts', before: 'game?.free();', after: '', test: 'search-engine' },
  { name: 'worker-easy-terminal', file: 'ai/search-engine.ts', before: "if (result.stopReason !== 'terminal')", after: 'if (true)', test: 'search-engine' },
  { name: 'store-revision', file: 'game/store.ts', before: 'this.revision += 1;', after: 'this.revision += 0;', test: 'store' },
  { name: 'store-root-revision', file: 'game/store.ts', before: 'root.revision !== s.revision || ', after: '', test: 'store' },
  { name: 'store-abandoned', file: 'game/store.ts', before: 'legal: g.isFinished() ? [] : g.legalMoves(),', after: 'legal: result ? [] : g.legalMoves(),', test: 'store' },
  { name: 'ui-obsolete-file-read', file: 'App.tsx', before: 'if (generation !== importGeneration.current) return;', after: '', test: 'app-import', extension: 'tsx' },
  { name: 'arena-pause-cancel', file: 'ai/arena-controller.ts', before: 'if (this.pending) this.client.cancel();', after: '', test: 'arena-controller' },
  { name: 'arena-late-success', file: 'ai/arena-controller.ts', before: '}).then((reply) => {\n        if (this.disposed || generation !== this.generation) return;', after: '}).then((reply) => {\n        if (this.disposed) return;', test: 'arena-controller' },
  { name: 'arena-start-paused', file: 'ai/arena-controller.ts', before: '(!this.options.running && !single)', after: 'false', test: 'arena-controller' },
  { name: 'arena-step-delay', file: 'ai/arena-controller.ts', before: 'single ? 0 : this.options.delayMs', after: 'this.options.delayMs', test: 'arena-controller' },
  { name: 'arena-error-fallback', file: 'ai/arena-controller.ts', before: "if (this.state.error) { this.publish('error'); return; }", after: '', test: 'arena-controller' },
  { name: 'arena-human-turn', file: 'ai/arena-controller.ts', before: "if (this.human()) { this.publish('human'); return; }", after: '', test: 'arena-controller' },
  { name: 'arena-speed-erases-step', file: 'ai/arena-controller.ts', before: ' && !this.scheduledSingle', after: '', test: 'arena-controller' },
  { name: 'render-ready-before-geometry', file: 'renderer/RenderReady.tsx', before: 'gl.info.render.triangles > 0', after: 'true', test: 'render-ready', extension: 'tsx' },
  { name: 'render-ready-duplicate', file: 'renderer/RenderReady.tsx', before: 'if (!reported.current && gl.info.render.triangles > 0)', after: 'if (gl.info.render.triangles > 0)', test: 'render-ready', extension: 'tsx' },
  { name: 'render-ready-demand-frame', file: 'renderer/RenderReady.tsx', before: 'if (!reported.current && gl.info.render.triangles === 0) invalidate();', after: '', test: 'render-ready', extension: 'tsx' },
];

function main() {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const web = join(root, 'apps/web');
  const output = join(root, 'coverage/web-mutations');
  mkdirSync(output, { recursive: true });
  const work = mkdtempSync(join(tmpdir(), 'voxelshogi-web-mutations-'));
  const copy = join(work, 'apps/web');
  const results = [];
  const run = (name, tests = []) => {
    const reportPath = join(work, 'vitest-result.json');
    rmSync(reportPath, { force: true });
    const result = spawnSync(process.execPath, [join(web, 'node_modules/vitest/vitest.mjs'), 'run', ...tests, '--reporter=json', `--outputFile=${reportPath}`], {
      cwd: copy, encoding: 'utf8', timeout: 60_000, maxBuffer: 8 * 1024 * 1024,
    });
    writeFileSync(join(output, `${name}.log`), `${result.stdout ?? ''}\n${result.stderr ?? ''}`);
    let report;
    try { report = JSON.parse(readFileSync(reportPath, 'utf8')); } catch { /* no report is an infrastructure error */ }
    if (report) writeFileSync(join(output, `${name}.json`), JSON.stringify(report, null, 2) + '\n');
    return classifyVitest(result, report);
  };
  try {
    mkdirSync(copy, { recursive: true });
    assert.ok(existsSync(join(web, 'src/wasm/pkg/voxelshogi_wasm_bg.wasm')), 'Build WASM before running web mutations');
    for (const path of ['src', 'tests', 'public', 'vite.config.ts', 'package.json']) cpSync(join(web, path), join(copy, path), { recursive: true });
    const fixtures = join(work, 'crates/voxelshogi-wasm/tests/fixtures');
    mkdirSync(fixtures, { recursive: true });
    cpSync(join(root, 'crates/voxelshogi-wasm/tests/fixtures/search.json'), join(fixtures, 'search.json'));
    symlinkSync(join(web, 'node_modules'), join(copy, 'node_modules'), 'dir');
    assert.equal(run('baseline'), 'passed', 'Original web tests must pass before mutation');
    for (const mutation of mutations) {
      const path = join(copy, 'src', mutation.file);
      const original = readFileSync(path, 'utf8');
      assert.equal(original.split(mutation.before).length - 1, 1, `Stale mutation anchor: ${mutation.name}`);
      try {
        writeFileSync(path, original.replace(mutation.before, mutation.after));
        const outcome = run(mutation.name, [`tests/${mutation.test}.test.${mutation.extension ?? 'ts'}`]);
        results.push({ name: mutation.name, outcome });
        console.log(`${mutation.name}: ${outcome}`);
        assert.equal(outcome, 'caught', `Mutation not caught by an executed assertion: ${mutation.name}`);
      } finally { writeFileSync(path, original); }
    }
    assert.equal(results.length, 29);
  } finally {
    writeFileSync(join(output, 'results.json'), JSON.stringify({ results }, null, 2) + '\n');
    rmSync(work, { recursive: true, force: true });
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) main();
