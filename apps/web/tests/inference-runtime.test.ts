import { createHash } from 'node:crypto';
import { afterEach, expect, it, vi } from 'vitest';
import { loadPackage } from '../src/inference/runtime';
import { deploymentFixture, modelFixture } from './inference-fixtures';

afterEach(() => vi.unstubAllGlobals());
const hash = (text: string) => createHash('sha256').update(text).digest('hex');
function server(corrupt = false) {
  const base = 'https://example.test/models/m3/', model = JSON.stringify(modelFixture()), index = deploymentFixture();
  index.model = { ...index.model, bytes: new TextEncoder().encode(model).length, sha256: hash(model) };
  index.modelNotices = index.modelNotices.map((f, i) => ({ ...f, bytes: 3, sha256: hash(i === 0 ? 'abc' : 'def') }));
  const files = new Map([[base + 'index.json', JSON.stringify(index)], [base + index.model.path, model],
    [base + index.modelNotices[0]!.path, corrupt ? 'abd' : 'abc'], [base + index.modelNotices[1]!.path, 'def']]);
  const fetcher = vi.fn(async (input: string) => new Response(files.get(input) ?? 'missing', { status: files.has(input) ? 200 : 404 }));
  vi.stubGlobal('fetch', fetcher);
  return { base, index, fetcher };
}

it('verifies model notices before returning a public package', async () => {
  const s = server(), pkg = await loadPackage(s.base + 'index.json');
  expect(pkg.packageHash).toBe(s.index.model.sha256);
  expect(pkg.index.modelNotices).toHaveLength(2);
  expect(s.fetcher.mock.calls.map(c => c[0])).toContain(s.base + s.index.modelNotices[0]!.path);
});

it('rejects a modified license notice even when its declared byte count is correct', async () => {
  const s = server(true);
  await expect(loadPackage(s.base + 'index.json')).rejects.toThrow(/hash/i);
});
