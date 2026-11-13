import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('layout screenshots are uploaded before a second Playwright invocation cleans its output', () => {
  const workflow = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8');
  const suite = workflow.indexOf('      - run: pnpm e2e\n');
  const save = workflow.indexOf('      - name: Save launch layout evidence\n');
  const repeat = workflow.indexOf('      - name: Repeat search and camera regression without retries\n');
  assert.ok(suite >= 0 && save > suite && repeat > save, 'save layout images after the full suite and before output cleanup');
  const upload = workflow.slice(save, repeat);
  assert.ok(upload.includes('apps/web/test-results/launch-*/attachments/*.png'));
  assert.ok(upload.includes('if-no-files-found: error'));
  assert.ok(!upload.includes('path: apps/web/test-results\n'), 'only the synthetic layout images belong in this artifact');
});
