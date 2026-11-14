import { assetUrl, fetchVerified, type FileRef } from './assets';
import { loadLocalModel, parseTrainedCatalog, readTrainedCatalog, type LocalModel, type TrainedRelease } from './local-model';
import { parseTrainedModel } from './manifest';

/** Public S only. Main thread reads small metadata; the Worker lazily fetches weights/references. */
export async function loadPublicModel(value: unknown, signal?: AbortSignal, fetcher: typeof fetch = globalThis.fetch.bind(globalThis), origin = globalThis.location?.origin): Promise<LocalModel> {
  const release = parseTrainedCatalog({ schema: 1, releases: [value] })[0]!;
  if (release.publicDownload !== true) throw new Error('public model download is not approved');
  signal?.throwIfAborted();
  const host = origin ? new URL(origin).hostname : 'localhost';
  const base = ['localhost', '127.0.0.1', '[::1]'].includes(host)
    ? `https://huggingface.co/${release.repo}/resolve/${release.revision}/`
    : new URL(`/api/models/s/${release.revision}/`, origin).href;
  const read = (file: FileRef, readSignal = signal) => fetchVerified(assetUrl(base, file.path), file, readSignal, fetcher);
  const manifest = await read(release.manifest);
  const model = parseTrainedModel(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(manifest)), release);
  const files = new Map<string, FileRef>();
  const include = (file: FileRef) => {
    const previous = files.get(file.path);
    if (previous && (previous.bytes !== file.bytes || previous.sha256 !== file.sha256)) throw new Error('conflicting public asset descriptors');
    files.set(file.path, { ...file });
  };
  [release.manifest, ...release.notices, ...model.fixtures.map(f => f.input)].forEach(include);
  for (const variant of model.variants) {
    include(variant.model);
    for (const reference of Object.values(variant.references)) { include(reference.policy); include(reference.value); }
  }
  // Reuse the local package's full identity/notice/inventory checks without eager binary reads.
  const source = await loadLocalModel([...files.values()].map(file => ({
    name: file.path.split('/').at(-1)!, webkitRelativePath: `public/${file.path}`, size: file.bytes,
    arrayBuffer: async () => (file.path === 'manifest.json' ? manifest : await read(file)).buffer,
  })), release, signal);
  return { ...source, read: async (file, readSignal) => {
    const expected = files.get(file.path);
    if (!expected || expected.bytes !== file.bytes || expected.sha256 !== file.sha256) throw new Error('unknown or unlisted public asset');
    return read(expected, readSignal);
  } };
}

export async function preparePublicModel(signal?: AbortSignal) {
  const releases = parseTrainedCatalog(await readTrainedCatalog('/models/m6/catalog.json', globalThis.fetch.bind(globalThis), signal));
  const release: TrainedRelease | undefined = releases.find(item => item.publicDownload === true);
  if (!release) throw new Error('公開Sモデルの配布情報を取得できませんでした');
  const source = await loadPublicModel(release, signal);
  return { release: source.release, model: source.model, files: [] };
}
