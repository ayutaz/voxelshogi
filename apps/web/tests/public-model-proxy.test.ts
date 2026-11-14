import { expect, it, vi } from 'vitest';
import { publicModelAsset } from '../src/collection/public-model-proxy';

const revision = '6ab524574d36536348dbe323a2b779b9cebe37ed';
const url = (path: string) => `https://game.example/api/models/s/${revision}/${path}`;
it('streams the pinned public S through the site without forwarding any user credentials', async () => {
  const fetcher = vi.fn(async () => new Response('public bytes', { headers: { 'content-type': 'application/octet-stream', 'set-cookie': 'unwanted=1' } }));
  const response = await publicModelAsset(new Request(url('int8.onnx'), { headers: { authorization: 'Bearer user-secret', cookie: 'session=private' } }), fetcher);
  expect(await response.text()).toBe('public bytes');
  expect(response.headers.get('set-cookie')).toBeNull();
  expect(response.headers.get('cache-control')).toContain('immutable');
  expect(fetcher).toHaveBeenCalledWith(`https://huggingface.co/voxelshogi/voxelshogi-transformer-s/resolve/${revision}/int8.onnx`, expect.objectContaining({ method: 'GET', credentials: 'omit', headers: { accept: 'application/octet-stream' } }));
});
it('allows exactly the 34 browser assets, without datasets, checkpoints, arbitrary repos or revisions', async () => {
  const fetcher = vi.fn(async () => new Response('asset'));
  const names = ['initial-b','after-one-w','mate-in-one-b','material-b'];
  const paths = ['manifest.json','README.md','LICENSE', ...names.map(n=>`inputs/${n}.f32`), ...['fp32','fp16','int8'].flatMap(p=>[`${p}.onnx`, ...names.flatMap(n=>[`reference/${p}/${n}-policy.f32`,`reference/${p}/${n}-value.f32`])])];
  expect(paths).toHaveLength(34);
  for (const path of paths) expect((await publicModelAsset(new Request(url(path)),fetcher)).status).toBe(200);
  expect(fetcher).toHaveBeenCalledTimes(34);fetcher.mockClear();
  for (const path of [url('model.safetensors'),url('evaluation.json'),url('other.onnx'),url('manifest.json')+'?url=https://private.example',url('manifest.json').replace(revision,'f'.repeat(40)),url('../training-state/model.safetensors')]) {
    expect((await publicModelAsset(new Request(path),fetcher)).status).toBe(404);
  }
  expect(fetcher).not.toHaveBeenCalled();
});
it('supports HEAD and rejects upstream errors and unsupported methods without exposing their content', async () => {
  const fetcher = vi.fn(async () => new Response(null));
  expect((await publicModelAsset(new Request(url('fp32.onnx'),{method:'HEAD'}),fetcher)).status).toBe(200);
  expect(fetcher).toHaveBeenCalledWith(expect.any(String),expect.objectContaining({method:'HEAD'}));
  expect((await publicModelAsset(new Request(url('fp32.onnx'),{method:'POST'}),fetcher)).status).toBe(405);
  fetcher.mockResolvedValueOnce(new Response('upstream sensitive error',{status:403}));
  const failed=await publicModelAsset(new Request(url('manifest.json')),fetcher);
  expect(failed.status).toBe(502);expect(await failed.text()).not.toContain('sensitive');
  expect(failed.headers.get('cache-control')).toBe('no-store');
});
