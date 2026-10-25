import { existsSync, mkdirSync, readFileSync, realpathSync, renameSync, rmdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const intervalMs = 600_000
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const guidance = 'CI確認は .agents/skills/ci-checks/SKILL.md に従う。取得は最短10分間隔。CI待ちだけの短いwait/sleepの反復を使わず、別作業を進めるか未完了を明記する。報告は状態変更時だけ行い、必須CI未完了ではmergeしない。'
const deny = reason => ({ hookSpecificOutput: {
  hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: reason,
} })

function classifyGh(tail) {
  if (/--(?:method|request)\s+(?:POST|PUT|PATCH|DELETE)\b|\s-X\s*(?:POST|PUT|PATCH|DELETE)\b/i.test(tail)) return { status: false }
  if (/\brun\s+view\b/.test(tail) && /--log(?:-failed)?\b/.test(tail)) return { status: false }
  const status = /\brun\s+(?:view|list|watch)\b|\bpr\s+checks\b|\bpr\s+view\b[^\n]*(?:statusCheckRollup|mergeStateStatus)|\bapi\b[^\n]*(?:actions\/runs|check-runs|check-suites|commits\/[^\s]+\/status)/.test(tail)
  if (!status) return { status: false }
  const watch = /\brun\s+watch\b|--watch\b/.test(tail)
  const seconds = Number(tail.match(/(?:--interval(?:=|\s+)|-i\s+)(\d+)/)?.[1] ?? 0)
  return { status, fastWatch: watch && seconds < intervalMs / 1000 }
}

function classify(command) {
  const gh = /\bgh\s+(?:(?:-R|--repo)\s+\S+\s+)?/
  const commands = command.split(gh).slice(1).map(classifyGh)
  const status = commands.some(c => c.status)
  const loop = status && /\b(?:while|until|for)\b|setInterval\s*\(|setTimeout\s*\(/.test(command)
  return { status, fastWatch: commands.some(c => c.fastWatch), loop }
}

export function checkPolicy(event, { stateDir = join(root, '.codex/.local/ci-poll-guard'), nowMs = Date.now() } = {}) {
  if (event.hook_event_name === 'SessionStart') return { hookSpecificOutput: {
    hookEventName: 'SessionStart', additionalContext: guidance,
  } }
  if (event.hook_event_name !== 'PreToolUse') return {}
  const input = event.tool_input ?? {}
  const name = event.tool_name ?? ''
  const command = name === 'Bash' ? input.command ?? '' : ''
  const kind = classify(command)
  const wait = /^(?:(?:functions|clock)\.)?(?:wait|sleep)$/.test(name) || /^\s*sleep\s+\d/.test(command)
  if (kind.fastWatch || kind.loop) return deny('CIの短いwatch・独自監視ループは使えません。単発確認か --interval 600 以上を使ってください。')
  if (input.terminate === true) return {}
  // An orchestration wrapper is not independent work between CI and its wait.
  const wrapper = /^(?:functions\.)?exec$/.test(name)
  const stateFile = join(stateDir, 'state.json')
  const lock = join(stateDir, 'lock')
  if (!kind.status && !existsSync(stateFile)) return {}
  try {
    mkdirSync(stateDir, { recursive: true })
    mkdirSync(lock)
  } catch (error) {
    if (!kind.status && !wait) return {}
    return deny(error.code === 'EEXIST'
      ? 'CI確認の間隔を別の呼び出しが更新中です。連続して再試行しないでください。'
      : 'CI確認hookの状態を保存できません。設定・ローカル状態を確認してください。')
  }
  try {
    let state = { lastCheckAt: null, waitingSessions: [] }
    try { state = JSON.parse(readFileSync(stateFile, 'utf8')) } catch (error) {
      if (error.code !== 'ENOENT') throw error
    }
    if (!Array.isArray(state.waitingSessions) || (state.lastCheckAt !== null && !Number.isFinite(state.lastCheckAt))) throw new Error('Invalid polling state')
    const session = event.session_id ?? 'unknown'
    if (wait && state.waitingSessions.includes(session)) return deny('CI待ちだけのwait/sleep呼び出しは繰り返しません。別作業を進めるか、CI未完了と記録して戻ってください。')
    if (kind.status) {
      const elapsed = nowMs - (state.lastCheckAt ?? -Infinity)
      if (elapsed < intervalMs) return deny(`CI再取得まであと${Math.ceil((intervalMs - elapsed) / 1000)}秒です。短いwaitループで待たないでください。`)
      state.lastCheckAt = nowMs
      state.waitingSessions = [...new Set([...state.waitingSessions, session])]
    } else if (!wrapper && !wait) {
      state.waitingSessions = state.waitingSessions.filter(s => s !== session)
    } else return {}
    const temporary = join(stateDir, `state-${process.pid}.tmp`)
    writeFileSync(temporary, JSON.stringify(state), { mode: 0o600 })
    renameSync(temporary, stateFile)
    return {}
  } catch {
    return kind.status || wait ? deny('CI確認hookの状態を読み書きできません。ローカル状態を確認してください。') : {}
  } finally {
    rmdirSync(lock)
  }
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const event = JSON.parse(readFileSync(0, 'utf8'))
    process.stdout.write(`${JSON.stringify(checkPolicy(event))}\n`)
  } catch {
    process.stdout.write(`${JSON.stringify(deny('CI確認hookの状態を読み書きできません。設定・ローカル状態を確認してください。'))}\n`)
  }
}
