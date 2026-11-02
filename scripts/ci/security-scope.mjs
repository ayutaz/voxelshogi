import { appendFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const impactKeys = ['rust', 'web', 'python', 'models', 'dependencies', 'controls'];
const outputKeys = [...impactKeys, 'deep'];

export function codeqlRequired(scope, eventName) {
  if (scope?.result !== 'success') throw new Error('CodeQL scope must succeed');
  if (!outputKeys.every(key => ['true', 'false'].includes(scope.outputs?.[key]))) {
    throw new Error('CodeQL scope has invalid outputs');
  }
  if (eventName !== 'pull_request' && scope.outputs.deep !== 'true') {
    throw new Error('CodeQL scope must retain deep verification outside PRs');
  }
  // PR merge protection requires real CodeQL results, including prose-only changes.
  if (eventName !== 'push') return true;
  // Only a proven prose-only main push can omit duplicate extraction and analysis.
  return impactKeys.some(key => scope.outputs[key] === 'true');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const analyze = codeqlRequired(JSON.parse(process.env.SCOPE_JSON), process.env.GITHUB_EVENT_NAME);
  appendFileSync(process.env.GITHUB_OUTPUT, `analyze=${analyze}\n`);
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### CodeQL change scope\n\n${analyze ? 'All four languages require extraction and analysis.' : 'Proven documentation-only main push: extraction and analysis omitted; required checks validate scope.'}\n`);
}
