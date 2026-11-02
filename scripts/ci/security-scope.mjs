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
  // Only a proven prose-only PR/main comparison can omit extraction and analysis.
  if (!['pull_request', 'push'].includes(eventName)) return true;
  return impactKeys.some(key => scope.outputs[key] === 'true');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const analyze = codeqlRequired(JSON.parse(process.env.SCOPE_JSON), process.env.GITHUB_EVENT_NAME);
  appendFileSync(process.env.GITHUB_OUTPUT, `analyze=${analyze}\n`);
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### CodeQL change scope\n\n${analyze ? 'All four languages require extraction and analysis.' : 'Proven documentation-only comparison: extraction and analysis omitted; required checks validate scope.'}\n`);
}
