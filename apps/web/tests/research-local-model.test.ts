import { expect, it, vi } from 'vitest';
import { indexLocalFolder, loadLocalModel, parseTrainedCatalog } from '../src/inference/local-model';
import { packModelFiles, parsePolicyRequest } from '../src/inference/policy-protocol';
import { policyRequest } from './policy-worker-fixtures';
import { digest, ref, releaseFixture } from './local-model-fixtures';
import { researchFixture, researchIdentity } from './research-model-fixtures';

function entry(path: string, bytes: number, text = '') {
  return { name: path.split('/').at(-1)!, webkitRelativePath: `download/${path}`, size: bytes, arrayBuffer: vi.fn(async () => new TextEncoder().encode(text).buffer) };
}
function fixture() {
  const model = researchFixture(), manifest = JSON.stringify(model);
  const release = { ...releaseFixture(manifest), ...researchIdentity(), repo: 'voxelshogi/voxelshogi-transformer-m' };
  const files = [entry('manifest.json', new TextEncoder().encode(manifest).length, manifest), entry('README.md', 12, 'Fixture card'), entry('LICENSE', 15, 'Fixture license'), entry(model.checkpoint.path, model.checkpoint.bytes)];
  // The small evidence text is genuine fixture JSON, not evaluation/model data.
  for (const descriptor of [model.research.selection, ...model.variants.map(v => v.evaluation.report)]) {
    descriptor.bytes = 2; descriptor.sha256 = digest('{}'); files.push(entry(descriptor.path, 2, '{}'));
  }
  const text = JSON.stringify(model); release.manifest = ref('manifest.json', text); files[0] = entry('manifest.json', new TextEncoder().encode(text).length, text);
  for (const f of model.fixtures) files.push(entry(f.input.path, f.input.bytes));
  for (const v of model.variants) {
    files.push(entry(v.model.path, v.model.bytes));
    for (const r of Object.values(v.references)) for (const f of [r.policy, r.value]) files.push(entry(f.path, f.bytes));
  }
  return { model, release, files };
}

it('recognizes explicit M catalog profiles while refusing unknown and incomplete profile identities', () => {
  const f = fixture();
  expect(parseTrainedCatalog({ schema: 1, releases: [f.release] })[0]).toMatchObject(researchIdentity());
  for (const changes of [{ profile: 'unknown' }, { architecture: 'unknown' }, { architecture: undefined }, { profile: undefined }, { license: 'MIT' }]) {
    expect(() => parseTrainedCatalog({ schema: 1, releases: [{ ...f.release, ...changes }] })).toThrow();
  }
});

it('loads only pinned M metadata and leaves all large bodies lazy for the Worker', async () => {
  const f = fixture(), source = await loadLocalModel(f.files, f.release);
  expect(source.model.parameters).toBe(25_783_688);
  expect(source.packageHash).toBe(f.release.manifest.sha256);
  expect(f.files.filter(file => file.size > 1024 * 1024).every(file => file.arrayBuffer.mock.calls.length === 0)).toBe(true);
  for (const path of ['selection.json', 'evaluation/fp32.json', 'evaluation/fp16.json', 'evaluation/int8.json']) expect(f.files.find(file => file.name === path.split('/').at(-1))!.arrayBuffer).toHaveBeenCalledOnce();
  // Large payloads are deliberately absent: a read must still enforce actual bytes.
  await expect(source.read(source.model.variants[0]!.model)).rejects.toThrow(/length/i);
  await expect(source.read(ref('.env', 'secret'))).rejects.toThrow(/unknown|listed/i);
  await expect(source.read(f.model.checkpoint)).rejects.toThrow(/unknown|listed/i);
  // Original FP32 training weights stay on Linux/HF and are not browser inputs.
  await expect(loadLocalModel(f.files.filter(file => file.name !== 'model.safetensors'), f.release)).resolves.toMatchObject({ packageHash: f.release.manifest.sha256 });
});

it('rejects missing or changed M evidence before touching a model body', async () => {
  for (const path of ['selection.json', 'evaluation/int8.json']) {
    const f = fixture();
    await expect(loadLocalModel(f.files.filter(file => file.webkitRelativePath !== `download/${path}`), f.release)).rejects.toThrow(/missing/i);
  }
  const f = fixture(); f.files.find(file => file.webkitRelativePath === 'download/evaluation/fp16.json')!.arrayBuffer.mockResolvedValue(new TextEncoder().encode('[]').buffer);
  await expect(loadLocalModel(f.files, f.release)).rejects.toThrow(/hash/i);
  expect(f.files.filter(file => file.name.endsWith('.onnx')).every(file => file.arrayBuffer.mock.calls.length === 0)).toBe(true);
});

it('retains S limits and caps M file/directory metadata before any read', async () => {
  const large = entry('fp32.onnx', 138_880_000);
  expect(() => indexLocalFolder([large])).toThrow(/size/i);
  expect(() => indexLocalFolder([entry('a', 512 * 1024 * 1024 + 1)], 'research-m-v1')).toThrow(/size/i);
  expect(() => indexLocalFolder(['a', 'b', 'c', 'd'].map(name => entry(name, 512 * 1024 * 1024)), 'research-m-v1')).toThrow(/folder/i);
  const f = fixture(); const { profile: _profile, architecture: _architecture, ...legacy } = f.release;
  void _profile; void _architecture;
  await expect(loadLocalModel(f.files, legacy)).rejects.toThrow(/size/i);
  expect(f.files.every(file => file.arrayBuffer.mock.calls.length === 0)).toBe(true);
});

it('transfers bounded File handles without materializing large bodies before catalog approval', () => {
  const file = new File([''], 'fp32.onnx');
  Object.defineProperty(file, 'size', { value: 138_880_000 }); Object.defineProperty(file, 'webkitRelativePath', { value: 'download/fp32.onnx' });
  const read = vi.spyOn(file, 'arrayBuffer'), packed = packModelFiles([file]);
  expect(parsePolicyRequest({ ...policyRequest(false), files: packed }).files![0]!.file).toBe(file);
  expect(read).not.toHaveBeenCalled();
});

it('never turns the permissive transfer metadata index into a body reader', async () => {
  const file = entry('fp32.onnx', 3, 'abc');
  await expect(indexLocalFolder([file], 'transfer').read(ref('fp32.onnx', 'abc'))).rejects.toThrow(/approval/i);
  expect(file.arrayBuffer).not.toHaveBeenCalled();
});
