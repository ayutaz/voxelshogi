import { pathToFileURL } from 'node:url';

export function checkGate(needs, event) {
  if (!needs || Array.isArray(needs) || typeof needs !== 'object') throw new Error('Invalid needs results');
  return ['lint', 'rust', 'msrv', 'web', 'e2e-runtime', 'audit', 'dependency-review', 'python'].flatMap((name) => {
    const result = needs[name]?.result;
    if (name === 'dependency-review' && event !== 'pull_request' && result === 'skipped') return [];
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
