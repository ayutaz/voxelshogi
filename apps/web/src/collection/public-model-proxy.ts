// Only this already ungated, hash-pinned inference package may cross the gateway.
const REVISION = '6ab524574d36536348dbe323a2b779b9cebe37ed';
const fixtures = ['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b'];
const paths = ['manifest.json', 'README.md', 'LICENSE', ...fixtures.map(f => `inputs/${f}.f32`),
  ...['fp32', 'fp16', 'int8'].flatMap(p => [`${p}.onnx`, ...fixtures.flatMap(f => [`reference/${p}/${f}-policy.f32`, `reference/${p}/${f}-value.f32`])])];
const upstreams = new Map(paths.map(path => [`/api/models/s/${REVISION}/${path}`, `https://huggingface.co/voxelshogi/voxelshogi-transformer-s/resolve/${REVISION}/${path}`]));
const unavailable = () => new Response('Public model unavailable', { status: 502, headers: { 'cache-control': 'no-store' } });

/** Streams approved public bytes without forwarding any browser headers or token. */
export async function publicModelAsset(request: Request, fetcher: typeof fetch = globalThis.fetch.bind(globalThis)): Promise<Response> {
  const url = new URL(request.url), upstream = upstreams.get(url.pathname);
  if (!upstream || url.search) return new Response('Not found', { status: 404 });
  if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', { status: 405, headers: { allow: 'GET, HEAD' } });
  const options: RequestInit & { cf: { cacheEverything: boolean; cacheTtl: number } } = {
    method: request.method, credentials: 'omit', redirect: 'follow',
    headers: { accept: 'application/octet-stream' },
    cf: { cacheEverything: true, cacheTtl: 86400 },
  };
  try {
    const response = await fetcher(upstream, options);
    if (response.status !== 200) return unavailable();
    const headers = new Headers(response.headers);
    headers.delete('set-cookie');
    headers.set('cache-control', 'public, max-age=31536000, immutable');
    return new Response(request.method === 'HEAD' ? null : response.body, { status: 200, headers });
  } catch { return unavailable(); }
}
