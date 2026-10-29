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
  { name: 'model-notice-text-only', file: 'inference/local-model.ts', before: "!['README.md', 'LICENSE', 'NOTICE'].includes(file.path)", after: 'false', test: 'local-model' },
  { name: 'model-notice-size', file: 'inference/local-model.ts', before: 'file.bytes > 1024 * 1024', after: 'false', test: 'local-model' },
  { name: 'model-library-reselected-source', file: 'ai/model-library.ts', before: 'choice?.sourceId === previous.sourceId', after: 'false', test: 'model-library' },
  { name: 'model-library-precision', file: 'ai/model-library.ts', before: 'precision: choice.precision, backend: choice.backend', after: "precision: 'fp32', backend: choice.backend", test: 'model-library' },
  { name: 'model-library-remove', file: 'ai/model-library.ts', before: 'state.entries.filter(entry => entry.sourceId !== sourceId)', after: 'state.entries', test: 'model-library' },
  { name: 'model-library-limit', file: 'ai/model-library.ts', before: 'if (entries.length > 4)', after: 'if (false)', test: 'model-library' },
  { name: 'model-panel-late-completion', file: 'inference/ModelLibraryPanel.tsx', before: 'if (current !== generation.current) return;', after: '', test: 'model-library-panel', extension: 'tsx' },
  { name: 'model-panel-unmount-cancel', file: 'inference/ModelLibraryPanel.tsx', before: 'generation.current += 1; read.current?.abort();', after: '', test: 'model-library-panel', extension: 'tsx' },
  { name: 'arena-record-branch', file: 'ai/arena-record.ts', before: 'if (cursor >= shared)', after: 'if (false)', test: 'arena-record' },
  { name: 'arena-record-cursor', file: 'ai/arena-record.ts', before: 'ply < cursor', after: 'true', test: 'arena-record' },
  { name: 'arena-record-snapshot', file: 'ai/arena-record.ts', before: "structuredClone({ root, reply, ...(value.kind === 'model-result' ? {} : { search }) })", after: "{ root, reply, ...(value.kind === 'model-result' ? {} : { search }) }", test: 'arena-record' },
  { name: 'arena-record-accepted-only', file: 'ai/arena-controller.ts', before: 'else this.journal.accept(root, search, reply);', after: 'this.journal.accept(root, search, reply);', test: 'arena-model-controller' },
  { name: 'arena-model-source-key', file: 'ai/arena-model.ts', before: '[seat.sourceId, selection.modelId,', after: '[selection.modelId,', test: 'arena-client' },
  { name: 'arena-model-precision-key', file: 'ai/arena-model.ts', before: 'selection.packageHash, selection.precision, selection.backend', after: 'selection.packageHash, selection.backend', test: 'arena-client' },
  { name: 'arena-model-cache', file: 'ai/arena-client.ts', before: 'this.models.set(key, client);', after: '', test: 'arena-client' },
  { name: 'arena-model-remove-dispose', file: 'ai/arena-client.ts', before: 'client.dispose(); this.models.delete(key);', after: 'this.models.delete(key);', test: 'arena-client' },
  { name: 'arena-model-late-import', file: 'ai/arena-client.ts', before: 'if (this.active !== operation || this.disposed || !this.allowed.has(key)) { client.dispose(); throw aborted(); }', after: '', test: 'arena-client' },
  { name: 'arena-model-late-finally', file: 'ai/arena-client.ts', before: 'finally { if (this.active === operation) this.active = null; }\n  }\n  cancel()', after: 'finally { this.active = null; }\n  }\n  cancel()', test: 'arena-client' },
  { name: 'arena-model-source-snapshot', file: 'ai/arena-client.ts', before: 'seat.files.map(file => ({ ...file }))', after: 'seat.files', test: 'arena-client' },
  { name: 'arena-model-no-fallback', file: 'ai/arena-controller.ts', before: "if (input.difficulty !== 'model')", after: 'if (true)', test: 'arena-model-controller' },
  { name: 'arena-model-selected-conditions', file: 'ai/arena-controller.ts', before: 'modelSeatKey(expected) !== modelSeatKey(reply.model)', after: 'false', test: 'arena-model-controller' },
  { name: 'arena-model-config-key', file: 'ai/arena-controller.ts', before: "o.bDifficulty === 'model' && o.bModel ? modelSeatKey(o.bModel) : null", after: 'null', test: 'arena-model-controller' },
  { name: 'arena-model-human-seat', file: 'ai/arena-controller.ts', before: "this.options.mode !== 'h-r' && this.options.bDifficulty", after: 'this.options.bDifficulty', test: 'arena-model-controller' },
  { name: 'policy-client-terminate', file: 'inference/policy-client.ts', before: 'worker.terminate();', after: '', test: 'policy-client' },
  { name: 'policy-client-stale-callback', file: 'inference/policy-client.ts', before: 'this.worker !== worker || !this.pending', after: '!this.pending', test: 'policy-client' },
  { name: 'policy-client-stale-error', file: 'inference/policy-client.ts', before: 'if (this.worker === worker) this.fail(new Error(event.message', after: 'if (true) this.fail(new Error(event.message', test: 'policy-client' },
  { name: 'policy-client-duplicate-id', file: 'inference/policy-client.ts', before: 'data.requestId !== pending.request.requestId', after: 'false', test: 'policy-client' },
  { name: 'policy-client-source-snapshot', file: 'inference/policy-client.ts', before: 'source.files.map(entry => ({ ...entry }))', after: 'source.files', test: 'policy-client' },
  { name: 'policy-protocol-root-revision', file: 'inference/policy-protocol.ts', before: 'rootKeys.some(key => root[key] !== request.root[key])', after: "rootKeys.some(key => key !== 'revision' && root[key] !== request.root[key])", test: 'policy-protocol' },
  { name: 'policy-protocol-precision', file: 'inference/policy-protocol.ts', before: 'selectionKeys.every(key => first[key] === second[key])', after: "selectionKeys.every(key => key === 'precision' || first[key] === second[key])", test: 'policy-protocol' },
  { name: 'policy-protocol-complete-fixtures', file: 'inference/policy-protocol.ts', before: 'result.fixtures.length !== expectedFixtures.length', after: 'false', test: 'policy-protocol' },
  { name: 'policy-protocol-numeric-failure', file: 'inference/policy-protocol.ts', before: 'stats.exceeded !== 0', after: 'false', test: 'policy-protocol' },
  { name: 'policy-factory-catalog-hash', file: 'inference/policy-factory.ts', before: 'item.manifest.sha256 === selection.packageHash', after: 'true', test: 'policy-factory' },
  { name: 'policy-host-busy', file: 'inference/policy-host.ts', before: 'if (this.busy)', after: 'if (false)', test: 'policy-host' },
  { name: 'policy-host-reuse', file: 'inference/policy-host.ts', before: 'if (!this.active) {', after: 'if (true) {', test: 'policy-host' },
  { name: 'policy-worker-origin', file: 'inference/policy.worker.ts', before: "if (event.origin !== '') return;", after: '', test: 'policy-worker' },
  { name: 'policy-host-late-initialization', file: 'inference/policy-host.ts', before: "if (this.closed) { await prepared.session.dispose(); throw new DOMException('policy initialization cancelled', 'AbortError'); }", after: '', test: 'policy-host' },
  { name: 'policy-protocol-action-identity', file: 'inference/policy-protocol.ts', before: 'choice.action !== policyAction(choice.move, request.root.side)', after: 'false', test: 'policy-protocol' },
  { name: 'policy-protocol-main-file-read', file: 'inference/policy-protocol.ts', before: 'indexLocalFolder(files.map(localFile));', after: 'files.forEach(entry => { void entry.file.arrayBuffer(); }); indexLocalFolder(files.map(localFile));', test: 'policy-protocol' },
  { name: 'policy-session-input-reference', file: 'inference/policy-session.ts', before: 'input.some((byte, index) => byte !== encoded[index])', after: 'false', test: 'policy-session' },
  { name: 'policy-session-all-fixtures', file: 'inference/policy-session.ts', before: 'for (const fixture of model.fixtures)', after: 'for (const fixture of model.fixtures.slice(0, 1))', test: 'policy-session' },
  { name: 'policy-session-precision', file: 'inference/policy-session.ts', before: 'this.port.createSession(bytes, selection.precision)', after: "this.port.createSession(bytes, 'fp32')", test: 'policy-session' },
  { name: 'policy-session-cursor', file: 'inference/policy-session.ts', before: 'game.goto(root.cursor);', after: 'game.goto(0);', test: 'policy-session' },
  { name: 'policy-session-root-hash', file: 'inference/policy-session.ts', before: 'game.hash() !== root.hash', after: 'false', test: 'policy-session' },
  { name: 'policy-session-release', file: 'inference/policy-session.ts', before: 'await session?.release();', after: '', test: 'policy-session' },
  { name: 'policy-session-validation-output', file: 'inference/policy-session.ts', before: '} finally { outputs.dispose(); }', after: '} finally { /* mutated missing disposal */ }', test: 'policy-session' },
  { name: 'policy-session-move-output', file: 'inference/policy-session.ts', before: 'finally { outputs?.dispose(); }', after: 'finally { /* mutated missing disposal */ }', test: 'policy-session' },
  { name: 'policy-session-late-result', file: 'inference/policy-session.ts', before: 'this.live();\n        const choice = selectPolicyMove', after: 'const choice = selectPolicyMove', test: 'policy-session' },
  { name: 'policy-session-placement', file: 'inference/policy-session.ts', before: 'if (port.info.backend !== selection.backend || providers.length !== 1 || providers.some(([name, count]) => name !== expected || !Number.isSafeInteger(count) || count <= 0))', after: 'if (false)', test: 'policy-session' },
  { name: 'policy-session-failed-run', file: 'inference/policy-session.ts', before: '} catch (error) { this.disposed = true; throw error; }\n      finally { outputs?.dispose(); }', after: '} finally { outputs?.dispose(); }', test: 'policy-session' },
  { name: 'policy-session-rust-free', file: 'inference/policy-session.ts', before: '} finally { game.free(); }\n      this.live();', after: '} finally { /* mutated missing free */ }\n      this.live();', test: 'policy-session' },
  { name: 'policy-white-rotation', file: 'inference/policy-contract.ts', before: "board[side === 'b' ? cell : 728 - cell]", after: 'board[cell]', test: 'policy-contract' },
  { name: 'policy-white-ownership', file: 'inference/policy-contract.ts', before: '(piece - 1 + 14) % 28 + 1', after: 'piece', test: 'policy-contract' },
  { name: 'policy-hand-normalization', file: 'inference/policy-contract.ts', before: "hands[side === 'b' ? i : (i + 7) % 14]! / HAND_TOTALS[i % 7]!", after: "hands[side === 'b' ? i : (i + 7) % 14]! / 162", test: 'policy-contract' },
  { name: 'policy-drop-kind', file: 'inference/policy-contract.ts', before: 'HAND_KINDS.indexOf(move.drop!)', after: '(6 - HAND_KINDS.indexOf(move.drop!))', test: 'policy-contract' },
  { name: 'policy-promotion', file: 'inference/policy-contract.ts', before: '+ Number(move.promote)', after: '+ 0', test: 'policy-contract' },
  { name: 'policy-legal-only', file: 'inference/policy-contract.ts', before: 'const choices = legal.map(move =>', after: "const choices = ['111111', ...legal].map(move =>", test: 'policy-contract' },
  { name: 'policy-canonical-tie', file: 'inference/policy-contract.ts', before: '.sort((a, b) => a.action - b.action)', after: '.sort((a, b) => b.action - a.action)', test: 'policy-contract' },
  { name: 'policy-value-perspective', file: 'inference/policy-contract.ts', before: 'value: value[0]!, rawAction', after: "value: side === 'w' ? -value[0]! : value[0]!, rawAction", test: 'policy-contract' },
  { name: 'policy-last-finite', file: 'inference/policy-contract.ts', before: 'action < POLICY_ELEMENTS;', after: 'action < POLICY_ELEMENTS - 1;', test: 'policy-contract' },
  { name: 'local-model-approval', file: 'inference/local-model.ts', before: 'if (release.approved !== true)', after: 'if (false)', test: 'local-model' },
  { name: 'local-model-descriptor-snapshot', file: 'inference/local-model.ts', before: 'known.set(file.path, { ...file });', after: 'known.set(file.path, file);', test: 'local-model' },
  { name: 'local-model-unlisted-file', file: 'inference/local-model.ts', before: 'const expected = known.get(file.path);', after: 'const expected = file;', test: 'local-model' },
  { name: 'local-model-notice-hash', file: 'inference/local-model.ts', before: 'await Promise.all(release.notices.map(file => folder.read(file, signal)));', after: '', test: 'local-model' },
  { name: 'local-model-directory-limit', file: 'inference/local-model.ts', before: 'if (total > MAX_FOLDER)', after: 'if (false)', test: 'local-model' },
  { name: 'local-model-abort-before-read', file: 'inference/local-model.ts', before: 'signal?.throwIfAborted();\n    has(file);', after: 'has(file);', test: 'local-model' },
  { name: 'trained-model-cohort', file: 'inference/manifest.ts', before: 'training.evaluation_game_count !== 60', after: 'false', test: 'trained-manifest' },
  { name: 'trained-model-selected-epoch', file: 'inference/manifest.ts', before: 'progress.epoch < 1', after: 'false', test: 'trained-manifest' },
  { name: 'trained-model-m3-scope', file: 'inference/manifest.ts', before: 'm.trained !== trained', after: 'false', test: 'trained-manifest' },
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
  { name: 'inference-file-hash', file: 'inference/assets.ts', before: 'hash !== file.sha256', after: 'false', test: 'inference-assets' },
  { name: 'inference-last-output', file: 'inference/engine.ts', before: 'i < count;', after: 'i < count - 1;', test: 'inference-engine' },
  { name: 'inference-session-release', file: 'inference/engine.ts', before: 'await session.release();', after: '', test: 'inference-engine' },
  { name: 'inference-tensor-release', file: 'inference/engine.ts', before: 'outputs.dispose();', after: '', test: 'inference-engine' },
  { name: 'inference-provider-proof', file: 'inference/engine.ts', before: "if (port.info.backend !== request.backend || providers.length === 0 || providers.some(([name, count]) => name !== expected || !Number.isSafeInteger(count) || count <= 0))", after: 'if (false)', test: 'inference-engine' },
  { name: 'inference-warmup', file: 'inference/engine.ts', before: 'times.slice(warmup)', after: 'times', test: 'inference-engine' },
  { name: 'inference-median', file: 'inference/engine.ts', before: '(sorted[Math.floor((sorted.length - 1) / 2)]! + sorted[Math.ceil((sorted.length - 1) / 2)]!) / 2', after: 'sorted[Math.floor(sorted.length / 2)]!', test: 'inference-engine' },
  { name: 'inference-root-revision', file: 'inference/client.ts', before: 'received[key] !== pending.request[key]', after: "key !== 'revision' && received[key] !== pending.request[key]", test: 'inference-client' },
  { name: 'inference-stale-callback', file: 'inference/client.ts', before: 'this.worker !== worker || !this.pending', after: '!this.pending', test: 'inference-client' },
  { name: 'inference-terminate', file: 'inference/client.ts', before: 'worker.terminate();', after: '', test: 'inference-client' },
  { name: 'inference-repeat-worst-error', file: 'inference/engine.ts', before: 'Math.max(current[name].maxAbs, comparison[name].maxAbs)', after: 'current[name].maxAbs', test: 'inference-engine' },
  { name: 'model-ui-stale-success', file: 'inference/ModelDemo.tsx', before: "if (current !== generation.current) return;\n      setResult(reply);", after: 'setResult(reply);', test: 'model-demo', extension: 'tsx' },
  { name: 'model-ui-stale-progress', file: 'inference/ModelDemo.tsx', before: 'if (current === generation.current) setState(phase);', after: 'setState(phase);', test: 'model-demo', extension: 'tsx' },
  { name: 'model-ui-cancel-change', file: 'inference/ModelDemo.tsx', before: 'generation.current++; revision.current++; client.current?.cancel();', after: 'generation.current++; revision.current++;', test: 'model-demo', extension: 'tsx' },
  { name: 'model-ui-dispose', file: 'inference/ModelDemo.tsx', before: 'instance.dispose();', after: '', test: 'model-demo', extension: 'tsx' },
  { name: 'inference-int8-optimization', file: 'inference/options.ts', before: "precision === 'int8' ? 'basic' : 'all'", after: "'all'", test: 'inference-options' },
  { name: 'inference-fp32-difference', file: 'inference/manifest.ts', before: "v.precision !== 'fp32'", after: 'false', test: 'inference-manifest' },
  { name: 'inference-cached-precision', file: 'inference/engine.ts', before: 'port.createSession(model, variant.precision)', after: "port.createSession(model, 'fp32')", test: 'inference-engine' },
  { name: 'inference-decoded-transfer', file: 'inference/resources.ts', before: 'decodedBytes: e.decodedBodySize', after: 'decodedBytes: e.encodedBodySize', test: 'inference-resources' },
  { name: 'inference-model-notices', file: 'inference/manifest.ts', before: 'index.publication && modelNotices.length < 2', after: 'false', test: 'inference-manifest' },
  { name: 'inference-notice-verification', file: 'inference/runtime.ts', before: 'await Promise.all(index.modelNotices.map(file => fetchVerified(assetUrl(assetBase, file.path), file, signal)));', after: '', test: 'inference-runtime' },
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
    mkdirSync(join(work, 'export/fixtures'), { recursive: true });
    cpSync(join(root, 'export/fixtures/positions.json'), join(work, 'export/fixtures/positions.json'));
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
    assert.equal(results.length, 119);
  } finally {
    writeFileSync(join(output, 'results.json'), JSON.stringify({ results }, null, 2) + '\n');
    rmSync(work, { recursive: true, force: true });
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) main();
