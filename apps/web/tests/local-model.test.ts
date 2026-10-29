import { afterEach, expect, it, vi } from 'vitest';
import { indexLocalFolder, loadLocalModel, parseTrainedCatalog } from '../src/inference/local-model';
import { digest, ref, releaseFixture, trainedFixture } from './local-model-fixtures';

afterEach(() => vi.unstubAllGlobals());
it('limits main-thread notices to small card/license text, never model bodies', () => {
  for (const notice of [ref('weights.onnx', 'abc'), { ...ref('NOTICE', 'abc'), bytes: 1024 * 1024 + 1 }]) {
    const release = releaseFixture(); release.notices.push(notice);
    expect(() => parseTrainedCatalog({ schema: 1, releases: [release] })).toThrow(/notice|descriptor/i);
  }
  const release = releaseFixture(); release.notices.push(ref('NOTICE', 'attribution'));
  expect(parseTrainedCatalog({ schema: 1, releases: [release] })[0]!.notices).toHaveLength(3);
});
function entry(path: string, text: string, size = new TextEncoder().encode(text).length) {
  const arrayBuffer = vi.fn(async () => new TextEncoder().encode(text).buffer);
  return { name: path.split('/').at(-1)!, webkitRelativePath: path, size, arrayBuffer };
}
function packageFixture() {
  const model = trainedFixture();
  model.variants[0]!.model = ref('fp32.onnx', 'abc');
  // Only the metadata is real in this pure fixture. No model/tensor is executed.
  const manifest = JSON.stringify(model), release = releaseFixture(manifest);
  const files = [entry('download/manifest.json', manifest), entry('download/README.md', 'Fixture card'), entry('download/LICENSE', 'Fixture license'),
    entry('download/fp32.onnx', 'abc'), entry('download/inputs/initial.f32', '', 125388),
    entry('download/reference/policy.f32', '', 4271940), entry('download/reference/value.f32', '', 4), entry('download/.env', 'must not read')];
  return { files, model, release };
}

it('accepts an empty public catalog without granting approval to an arbitrary local model', () => {
  expect(parseTrainedCatalog({ schema: 1, releases: [] })).toEqual([]);
  expect(parseTrainedCatalog({ schema: 1, releases: [releaseFixture()] })).toHaveLength(1);
  for (const field of ['approved', 'repo', 'revision', 'hash', 'duplicate', 'notices']) {
    const release = releaseFixture();
    if (field === 'approved') release.approved = false;
    if (field === 'repo') release.repo = 'another/model';
    if (field === 'revision') release.revision = 'main';
    if (field === 'hash') release.manifest.sha256 = 'bad';
    if (field === 'notices') release.notices = [];
    expect(() => parseTrainedCatalog({ schema: 1, releases: field === 'duplicate' ? [release, release] : [release] })).toThrow();
  }
});

it('reads the exact known SHA-256 body locally and never fetches or reads unrelated files', async () => {
  const fetcher = vi.fn(() => { throw new Error('no network allowed'); });
  vi.stubGlobal('fetch', fetcher);
  const fixture = packageFixture();
  const loaded = await loadLocalModel(fixture.files, fixture.release);
  expect(loaded.packageHash).toBe(digest(JSON.stringify(fixture.model)));
  expect(loaded.model.id).toBe(fixture.model.id);
  const bytes = await loaded.read(loaded.model.variants[0]!.model);
  expect(new TextDecoder().decode(bytes)).toBe('abc');
  await expect(loaded.read(ref('.env', 'must not read'))).rejects.toThrow(/listed|unknown/i);
  expect(fixture.files.at(-1)!.arrayBuffer).not.toHaveBeenCalled();
  expect(fixture.files[4]!.arrayBuffer).not.toHaveBeenCalled();
  expect(fetcher).not.toHaveBeenCalled();
});

it('rejects an unapproved release before reading the selected files', async () => {
  const fixture = packageFixture(); fixture.release.approved = false;
  await expect(loadLocalModel(fixture.files, fixture.release)).rejects.toThrow(/approv/i);
  expect(fixture.files.every(f => f.arrayBuffer.mock.calls.length === 0)).toBe(true);
});

it('checks the manifest before notices or model reads, even if the declared size matches', async () => {
  const fixture = packageFixture();
  fixture.files[0] = entry('download/manifest.json', JSON.stringify(fixture.model).replace('314159', '314150'));
  await expect(loadLocalModel(fixture.files, fixture.release)).rejects.toThrow(/hash/i);
  expect(fixture.files.slice(1).every(f => f.arrayBuffer.mock.calls.length === 0)).toBe(true);
});

it('verifies card and license files and requires every listed model/reference file', async () => {
  const fixture = packageFixture();
  fixture.files[1] = entry('download/README.md', 'Fixture care');
  await expect(loadLocalModel(fixture.files, fixture.release)).rejects.toThrow(/hash/i);
  const missing = packageFixture();
  await expect(loadLocalModel(missing.files.filter(f => !f.name.endsWith('.onnx')), missing.release)).rejects.toThrow(/missing/i);
});

it('checks selected model bytes on each read, without caching a corrupted body', async () => {
  const fixture = packageFixture();
  fixture.files[3] = entry('download/fp32.onnx', 'abd');
  const loaded = await loadLocalModel(fixture.files, fixture.release);
  await expect(loaded.read(loaded.model.variants[0]!.model)).rejects.toThrow(/hash/i);
});

it('does not let changes to returned metadata rewrite the reviewed asset identity', async () => {
  const fixture = packageFixture();
  const loaded = await loadLocalModel(fixture.files, fixture.release);
  const model = loaded.model.variants[0]!.model;
  model.sha256 = digest('abd');
  fixture.files[3]!.arrayBuffer.mockImplementation(async () => new TextEncoder().encode('abd').buffer);
  await expect(loaded.read(model)).rejects.toThrow(/listed|unknown/i);
});

it('bounds reads before allocating and honors cancellation before and after a disk read', async () => {
  const file = entry('folder/weights.onnx', 'abc'), reader = indexLocalFolder([file]);
  await expect(reader.read(ref('weights.onnx', 'abcd'))).rejects.toThrow(/size/i);
  const signal = new AbortController(); signal.abort();
  await expect(reader.read(ref('weights.onnx', 'abc'), signal.signal)).rejects.toMatchObject({ name: 'AbortError' });
  expect(file.arrayBuffer).not.toHaveBeenCalled();
  const during = new AbortController(), source = entry('folder/weights.onnx', 'abc');
  source.arrayBuffer.mockImplementation(async () => { during.abort(); return new TextEncoder().encode('abc').buffer; });
  await expect(indexLocalFolder([source]).read(ref('weights.onnx', 'abc'), during.signal)).rejects.toMatchObject({ name: 'AbortError' });
});

for (const path of ['../manifest.json', 'folder/../manifest.json', '/manifest.json', 'folder/a\\b', 'folder//a', 'folder/./manifest.json', 'manifest.json']) {
  it(`rejects unsafe or incomplete folder paths: ${path}`, () => expect(() => indexLocalFolder([entry(path, 'abc')])).toThrow());
}

it('rejects duplicate paths, multiple roots, oversized files and unexpected descriptor aliases', async () => {
  for (const files of [[entry('a/x', 'abc'), entry('a/x', 'abc')], [entry('a/x', 'abc'), entry('b/y', 'def')],
    [entry('a/x', '', 1024 * 1024 * 1024)], [entry('a/x', 'abc', -1)], []]) expect(() => indexLocalFolder(files)).toThrow();
  const fixture = packageFixture();
  fixture.model.variants[0]!.references['initial-b']!.value = { path: 'fp32.onnx', bytes: 4, sha256: 'a'.repeat(64) };
  const text = JSON.stringify(fixture.model); fixture.files[0] = entry('download/manifest.json', text);
  await expect(loadLocalModel(fixture.files, releaseFixture(text))).rejects.toThrow(/conflict|descriptor/i);
});

it('bounds the total directory size and entry count using metadata only', () => {
  const files = Array.from({ length: 9 }, (_, i) => entry(`folder/${i}.onnx`, '', 64 * 1024 * 1024));
  expect(() => indexLocalFolder(files)).toThrow(/folder.*size/i);
  expect(files.every(file => file.arrayBuffer.mock.calls.length === 0)).toBe(true);
  expect(() => indexLocalFolder(Array.from({ length: 513 }, (_, i) => entry(`folder/${i}.json`, '')))).toThrow(/count/i);
});
