import { pathToFileURL } from 'node:url';

export function checkGate(needs, event) {
  if (!needs || Array.isArray(needs) || typeof needs !== 'object') throw new Error('Invalid needs results');
  const scopeKeys = ['models', 'rust', 'web', 'python', 'dependencies', 'controls'];
  const scope = needs.scope;
  const validScope = scope?.result === 'success' && scopeKeys.every((name) => ['true', 'false'].includes(scope.outputs?.[name]));
  return ['scope', 'lint', 'rust', 'msrv', 'web', 'e2e-runtime', 'audit', 'dependency-review', 'python', 'models', 'python-model-mutations', 'python-training-mutations'].flatMap((name) => {
    const result = needs[name]?.result;
    if (name === 'scope' && result === 'success' && !validScope) return ['scope: invalid outputs'];
    if (name === 'dependency-review' && event !== 'pull_request' && result === 'skipped') return [];
    if (validScope && result === 'skipped') {
      if (['audit', 'dependency-review'].includes(name) && scope.outputs.dependencies === 'false') return [];
      if (['python-model-mutations', 'python-training-mutations'].includes(name) && scope.outputs.python === 'false') return [];
    }
    return result === 'success' ? [] : [`${name}: ${result ?? 'missing result'}`];
  });
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const failures = checkGate(JSON.parse(process.env.NEEDS_JSON ?? '{}'), process.env.GITHUB_EVENT_NAME);
  if (failures.length) {
    console.error(failures.join('\n'));
    process.exitCode = 1;
  } else {
    console.log('All required CI checks succeeded.');
  }
}
