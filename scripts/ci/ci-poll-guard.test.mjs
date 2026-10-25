import assert from 'node:assert/strict'
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'
import { checkPolicy } from './ci-poll-guard.mjs'

const minute = 60_000
const start = 1_800_000_000_000
const bash = (command, session = 'session-a') => ({
  hook_event_name: 'PreToolUse', session_id: session,
  tool_name: 'Bash', tool_input: { command },
})
const waiting = (tool_name = 'functions.wait', input = {}) => ({
  hook_event_name: 'PreToolUse', session_id: 'session-a',
  tool_name, tool_input: { yield_time_ms: 50_000, ...input },
})
function fixture(t) {
  const stateDir = mkdtempSync(join(tmpdir(), 'voxelshogi-poll-guard-'))
  t.after(() => rmSync(stateDir, { recursive: true, force: true }))
  return (event, elapsed = 0) => checkPolicy(event, { stateDir, nowMs: start + elapsed })
}
const denied = result => result.hookSpecificOutput?.permissionDecision === 'deny'

test('CIの再取得は10分未満で拒否し、ちょうど10分で許可する', t => {
  const check = fixture(t)
  assert.equal(denied(check(bash('gh pr checks 4'))), false)
  assert.equal(denied(check(bash('gh pr checks 4'), 10 * minute - 1)), true)
  assert.equal(denied(check(bash('gh pr checks 4'), 10 * minute)), false)
})

test('別セッションや別のCI取得コマンドでも同じリポジトリの間隔を守る', t => {
  const check = fixture(t)
  check(bash('gh pr view 4 --json statusCheckRollup'))
  assert.equal(denied(check(bash('gh api repos/ayutaz/voxelshogi/actions/runs/42/jobs', 'session-b'), minute)), true)
})

test('ログ調査と取得をまとめても、状態取得の間隔は短縮しない', t => {
  const check = fixture(t)
  check(bash('gh pr checks 4'))
  assert.equal(denied(check(bash('gh run view 42 --log-failed\ngh pr checks 4'), minute)), true)
})

test('CIを確認した直後の短いwait・sleepを拒否し、監視終了は許可する', t => {
  const check = fixture(t)
  check(bash('gh run view 42 --json status,conclusion'))
  assert.equal(denied(check(waiting(), minute)), true)
  assert.equal(denied(check(waiting('clock.sleep', { duration_ms: 60_000 }), minute)), true)
  assert.equal(denied(check(bash('sleep 30'), minute)), true)
  assert.equal(denied(check(waiting('functions.wait', { terminate: true }), minute)), false)
})

test('別の実作業を挟んだ後のビルド待ちを拒否しない', t => {
  const check = fixture(t)
  check(bash('gh pr checks 4'))
  assert.equal(denied(check(bash('cargo test --workspace'), minute)), false)
  assert.equal(denied(check(waiting(), minute)), false)
})

test('CI文脈のないwaitと別セッションのビルド待ちは許可する', t => {
  const check = fixture(t)
  assert.equal(denied(check(waiting())), false)
  check(bash('gh pr checks 4', 'session-b'))
  assert.equal(denied(check(waiting(), minute)), false)
})

test('失敗ログ調査・差分・merge・通常のテストは間隔制限の対象にしない', t => {
  const check = fixture(t)
  check(bash('gh pr checks 4'))
  for (const command of [
    'gh run view 42 --log-failed', 'gh pr diff 4', 'gh pr merge 4 --squash',
    'node --test scripts/ci/*.test.mjs',
    'gh api --method POST repos/ayutaz/voxelshogi/actions/runs/42/rerun',
  ]) assert.equal(denied(check(bash(command), minute)), false, command)
})

test('watchの既定・短い間隔と独自の無限監視ループを拒否する', t => {
  const check = fixture(t)
  for (const command of [
    'gh run watch 42', 'gh run watch 42 --interval 599',
    'gh pr checks 4 --watch -i 5',
    'while true; do gh pr checks 4; sleep 30; done',
  ]) assert.equal(denied(check(bash(command))), true, command)
  assert.equal(denied(check(bash('gh run watch 42 --interval 600'))), false)
})

test('他のリポジトリのCI確認を制限しない', t => {
  const first = fixture(t)
  const other = fixture(t)
  first(bash('gh pr checks 4'))
  assert.equal(denied(other(bash('gh pr checks 4'), minute)), false)
})

test('SessionStartはスキルと待機方針を通知し、取得履歴を消さない', t => {
  const check = fixture(t)
  check(bash('gh pr checks 4'))
  const result = check({ hook_event_name: 'SessionStart', session_id: 'session-b' })
  assert.match(result.hookSpecificOutput.additionalContext, /ci-checks/)
  assert.equal(denied(check(bash('gh pr checks 4', 'session-b'), minute)), true)
})

test('壊れた状態ファイルはCI取得を拒否するが修復コマンドを妨げない', t => {
  const stateDir = mkdtempSync(join(tmpdir(), 'voxelshogi-poll-corrupt-'))
  t.after(() => rmSync(stateDir, { recursive: true, force: true }))
  writeFileSync(join(stateDir, 'state.json'), '{broken')
  assert.equal(denied(checkPolicy(bash('gh pr checks 4'), { stateDir })), true)
  assert.equal(denied(checkPolicy(bash('git status --short'), { stateDir })), false)
})

test('実際のhookプロセスがstdinを読み、再取得拒否のJSONを返す', t => {
  const project = mkdtempSync(join(tmpdir(), 'voxelshogi-hook-process-'))
  t.after(() => rmSync(project, { recursive: true, force: true }))
  const directory = join(project, 'scripts/ci')
  mkdirSync(directory, { recursive: true })
  const script = join(directory, 'ci-poll-guard.mjs')
  copyFileSync(new URL('./ci-poll-guard.mjs', import.meta.url), script)
  const invoke = event => {
    const result = spawnSync(process.execPath, [script], { input: JSON.stringify(event), encoding: 'utf8' })
    assert.equal(result.status, 0, result.stderr)
    return JSON.parse(result.stdout)
  }
  assert.equal(denied(invoke(bash('gh pr checks 4'))), false)
  assert.equal(denied(invoke(bash('gh pr checks 4'))), true)
  assert.equal(denied(invoke(waiting())), true)
})
