import { appendFileSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const keys = ['rust', 'web', 'python', 'models', 'dependencies', 'controls'];
const full = () => Object.fromEntries(keys.map(k => [k, true]));
const shared = new Set(['Cargo.toml','Cargo.lock','rust-toolchain.toml','rustfmt.toml','pyproject.toml','uv.lock','.python-version','.node-version','.gitignore','apps/web/package.json','apps/web/pnpm-lock.yaml']);
export function classifyChanges(files) {
  if (!Array.isArray(files) || !files.length) return full();
  const result = Object.fromEntries(keys.map(k => [k, false]));
  for (const file of files) {
    if (shared.has(file) || /^(?:\.github\/|\.codex\/|\.agents\/|infrastructure\/|scripts\/ci\/)/.test(file)) return full();
    if (/^crates\//.test(file)) { for (const k of ['rust','web','python','models']) result[k] = true; }
    else if (/^training\//.test(file)) { result.python = true; result.models = true; }
    else if (/^export\//.test(file)) { result.python = true; result.models = true; result.web = true; }
    else if (/^apps\/web\//.test(file)) { result.web = true; result.models = true; }
    else if (/^docs\/.*\.md$/.test(file) || /^(?:README|CLAUDE|AGENTS|CONTRIBUTING|SECURITY|CODE_OF_CONDUCT)\.md$/.test(file)) { /* prose does not change executable inputs */ }
    else return full(); // New/unclassified input must not silently lose coverage.
  }
  return result;
}

export function verificationScope(files, eventName) {
  return { ...classifyChanges(files), deep: eventName !== 'pull_request' };
}

export function changedFiles(eventName, event, git = execFileSync) {
  if (!['pull_request','push'].includes(eventName)) return null;
  const base = eventName === 'pull_request' ? event.pull_request?.base?.sha : event.before;
  if (typeof base !== 'string' || !/^[0-9a-f]{40}$/.test(base) || /^0+$/.test(base)) return null;
  try {
    // Disable rename detection so deletions and additions both contribute impact.
    return git('git', ['diff','--name-only','--no-renames','-z',base,'HEAD'], { encoding:'utf8' }).split('\0').filter(Boolean);
  } catch { return null; }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'));
  const files = changedFiles(process.env.GITHUB_EVENT_NAME, event);
  const scope = verificationScope(files, process.env.GITHUB_EVENT_NAME);
  appendFileSync(process.env.GITHUB_OUTPUT, [...keys, 'deep'].map(k => `${k}=${scope[k]}\n`).join(''));
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### CI change scope\n\n${files === null ? 'All impact categories: manual/scheduled event or unavailable comparison.' : `Compared ${files.length} paths against the event base.`}\n\n` + keys.map(k => `- ${k}: ${scope[k] ? 'affected' : 'unaffected'}\n`).join('') + `- deep: ${scope.deep ? 'heavy verification enabled' : 'PR fast checks; heavy verification follows on main'}\n`);
}
