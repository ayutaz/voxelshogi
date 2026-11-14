import { afterEach, expect, it, vi } from 'vitest';
import { loadPublicModel } from '../src/inference/public-model';
import { ref, releaseFixture, trainedFixture } from './local-model-fixtures';

afterEach(() => vi.unstubAllGlobals());
it('uses the site origin for deployed browsers so HF CORS cannot block the model', async () => {
  const f=fixture(),fetcher=vi.fn(async()=>new Response('corrupt'));
  await expect(loadPublicModel(f.release,undefined,fetcher,'https://game.example')).rejects.toThrow();
  expect(fetcher).toHaveBeenCalledWith(`https://game.example/api/models/s/${f.release.revision}/manifest.json`,expect.objectContaining({credentials:'omit'}));
});
function fixture() {
  const model = trainedFixture(); model.variants[0]!.model = ref('fp32.onnx', 'abc');
  const manifest = JSON.stringify(model), release = { ...releaseFixture(manifest), publicDownload: true };
  const bodies: Record<string, string> = { 'manifest.json': manifest, 'README.md': 'Fixture card', LICENSE: 'Fixture license', 'fp32.onnx': 'abc' };
  const fetcher = vi.fn(async (url: string | URL | Request, options?: RequestInit) => {
    expect(options?.credentials).toBe('omit');
    expect(String(url).startsWith(`https://huggingface.co/${release.repo}/resolve/${release.revision}/`)).toBe(true);
    return new Response(bodies[String(url).split(`/${release.revision}/`)[1]!] ?? '', { status: 200 });
  });
  return { model, release, fetcher };
}
it('prepares only hash-verified metadata, then lazily reads the selected pinned model', async () => {
  const f = fixture();
  const source = await loadPublicModel(f.release, undefined, f.fetcher);
  expect(f.fetcher.mock.calls.map(([url]) => String(url).split('/').at(-1)).sort()).toEqual(['LICENSE', 'README.md', 'manifest.json']);
  expect(new TextDecoder().decode(await source.read(source.model.variants[0]!.model))).toBe('abc');
  expect(f.fetcher).toHaveBeenCalledTimes(4);
  await expect(source.read(ref('secret.txt', 'abc'))).rejects.toThrow(/unknown|listed/);
  expect(f.fetcher).toHaveBeenCalledTimes(4);
});
it('rejects unapproved public access and non-S repositories before network reads', async () => {
  for (const change of [{ publicDownload: undefined }, { publicDownload: false }, { repo: 'voxelshogi/another' }, { profile: 'research-m-v1', architecture: 'full' }]) {
    const f = fixture();
    const release = { ...f.release, ...change };
    if (Object.hasOwn(change, 'publicDownload') && change.publicDownload === undefined) Reflect.deleteProperty(release, 'publicDownload');
    await expect(loadPublicModel(release, undefined, f.fetcher)).rejects.toThrow();
    expect(f.fetcher).not.toHaveBeenCalled();
  }
});
it('rejects corrupt metadata/weights and honors cancellation without substituting a model', async () => {
  const f = fixture();
  await expect(loadPublicModel(f.release, undefined, async () => new Response('corrupt'))).rejects.toThrow();
  const source = await loadPublicModel(f.release, undefined, f.fetcher);
  f.fetcher.mockResolvedValueOnce(new Response('abd'));
  await expect(source.read(source.model.variants[0]!.model)).rejects.toThrow(/hash/);
  const abort = new AbortController(); abort.abort();
  await expect(loadPublicModel(f.release, abort.signal, f.fetcher)).rejects.toThrow();
  expect(f.fetcher).toHaveBeenCalledTimes(4);
});
