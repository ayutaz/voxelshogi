import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
test('candidate UI evidence excludes private model traces and survives camera output cleanup',()=>{
  const workflow=readFileSync(new URL('../../.github/workflows/demo-video.yml',import.meta.url),'utf8');
  const models=workflow.indexOf('      - name: Verify actual model formats and arena integration');
  const suite=workflow.indexOf('      - name: Verify all arena interactions and three screen sizes');
  const save=workflow.indexOf('      - name: Save only arena images, never private model traces');
  const repeat=workflow.indexOf('      - name: Repeat real search and camera regression');
  assert.ok(models>=0&&suite>models&&save>suite&&repeat>save);
  const upload=workflow.slice(save,repeat);
  const paths=upload.split('path: |\n')[1].split('          retention-days:')[0].trim().split('\n').map(s=>s.trim());
  assert.ok(paths.length>=2&&paths.every(p=>p.startsWith('apps/web/test-results/')&&p.endsWith('.png')),'allow only the controlled arena PNGs, never private model traces or binaries');
  assert.ok(upload.includes('if-no-files-found: error'));
});
