import { assetUrl, verifyBytes, type FileRef } from './assets';
import { parseTrainedModel, type ModelManifest, type TrainedIdentity } from './manifest';

export interface TrainedRelease extends TrainedIdentity {
  approved: true; repo: string; revision: string; manifest: FileRef; notices: FileRef[];
}
export interface LocalFile {
  name: string; webkitRelativePath: string; size: number; arrayBuffer: () => Promise<ArrayBuffer>;
}
export interface LocalFolder {
  has: (file: FileRef) => void;
  read: (file: FileRef, signal?: AbortSignal) => Promise<Uint8Array<ArrayBuffer>>;
}
export interface LocalModel {
  release: TrainedRelease; model: ModelManifest; packageHash: string;
  read: LocalFolder['read'];
}
const MAX_FILE = 64 * 1024 * 1024;
const MAX_FOLDER = 512 * 1024 * 1024;

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid catalog object');
  return value as Record<string, unknown>;
}
function descriptor(value: unknown): FileRef {
  const file = record(value);
  if (typeof file.path !== 'string' || typeof file.bytes !== 'number' || !Number.isSafeInteger(file.bytes) || file.bytes <= 0 || file.bytes > MAX_FILE || typeof file.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(file.sha256)) throw new Error('invalid local file descriptor');
  assetUrl('https://local.invalid/', file.path);
  return file as unknown as FileRef;
}

/** No embedded M6 weights or implicit release approval. An empty catalog is valid. */
export function parseTrainedCatalog(value: unknown): TrainedRelease[] {
  const catalog = record(value);
  if (catalog.schema !== 1 || !Array.isArray(catalog.releases) || catalog.releases.length > 16) throw new Error('unsupported trained catalog');
  const releases = catalog.releases.map(item => {
    const release = record(item);
    if (release.approved !== true) throw new Error('trained release approval is pending');
    if (typeof release.id !== 'string' || !/^[a-zA-Z0-9._-]{1,128}$/.test(release.id) || typeof release.license !== 'string' || !/^[A-Za-z0-9.-]{1,64}$/.test(release.license) || typeof release.sourceCommit !== 'string' || !/^[0-9a-f]{40}$/.test(release.sourceCommit) ||
      typeof release.repo !== 'string' || !/^voxelshogi\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(release.repo) || typeof release.revision !== 'string' || !/^[0-9a-f]{40}$/.test(release.revision)) throw new Error('invalid trained release identity');
    const manifest = descriptor(release.manifest);
    if (manifest.path !== 'manifest.json' || manifest.bytes > 1024 * 1024) throw new Error('invalid trained manifest descriptor');
    if (!Array.isArray(release.notices) || release.notices.length < 2 || release.notices.length > 16) throw new Error('trained release requires card/license notices');
    const notices = release.notices.map(descriptor), paths = notices.map(file => file.path);
    if (!paths.includes('README.md') || !paths.includes('LICENSE') || new Set(paths).size !== paths.length || paths.includes('manifest.json')) throw new Error('invalid trained card/license descriptors');
    return structuredClone({ ...release, manifest, notices }) as unknown as TrainedRelease;
  });
  if (new Set(releases.map(release => release.id)).size !== releases.length) throw new Error('duplicate trained model identity');
  return releases;
}

/** Indexes only metadata. Model bytes are read lazily by the dedicated Worker. */
export function indexLocalFolder(files: readonly LocalFile[]): LocalFolder {
  if (files.length < 1 || files.length > 512) throw new Error('invalid model folder file count');
  const entries = new Map<string, LocalFile>();
  let root: string | undefined, total = 0;
  for (const file of files) {
    const parts = file.webkitRelativePath.split('/'), folder = parts.shift()!, path = parts.join('/');
    if (!folder || folder === '.' || folder === '..' || /[\\\0]/.test(folder) || (root !== undefined && root !== folder) || file.webkitRelativePath.length > 1024) throw new Error('select one complete model folder');
    root = folder;
    assetUrl('https://local.invalid/', path);
    if (entries.has(path)) throw new Error('duplicate local file path');
    if (!Number.isSafeInteger(file.size) || file.size < 0 || file.size > MAX_FILE) throw new Error('local file size exceeds limit');
    total += file.size;
    if (total > MAX_FOLDER) throw new Error('model folder exceeds size limit');
    entries.set(path, file);
  }
  function has(value: FileRef) {
    const expected = descriptor(value), file = entries.get(expected.path);
    if (!file) throw new Error(`missing local model file: ${expected.path}`);
    if (file.size !== expected.bytes) throw new Error('local file size mismatch');
  }
  return { has, read: async (file, signal) => {
    signal?.throwIfAborted();
    has(file);
    const bytes = new Uint8Array(await entries.get(file.path)!.arrayBuffer());
    signal?.throwIfAborted();
    const verified = await verifyBytes(bytes, file);
    signal?.throwIfAborted();
    return verified;
  } };
}

export async function loadLocalModel(files: readonly LocalFile[], releaseValue: unknown, signal?: AbortSignal): Promise<LocalModel> {
  const release = parseTrainedCatalog({ schema: 1, releases: [releaseValue] })[0]!;
  const folder = indexLocalFolder(files);
  const bytes = await folder.read(release.manifest, signal);
  const model = parseTrainedModel(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)), release);
  const known = new Map<string, FileRef>();
  function list(file: FileRef) {
    const existing = known.get(file.path);
    if (existing && (existing.bytes !== file.bytes || existing.sha256 !== file.sha256)) throw new Error('conflicting local asset descriptors');
    folder.has(file);
    known.set(file.path, { ...file });
  }
  list(release.manifest); release.notices.forEach(list);
  for (const fixture of model.fixtures) list(fixture.input);
  for (const variant of model.variants) {
    list(variant.model);
    for (const reference of Object.values(variant.references)) { list(reference.policy); list(reference.value); }
  }
  await Promise.all(release.notices.map(file => folder.read(file, signal)));
  return { release, model, packageHash: release.manifest.sha256, read: async (file, readSignal) => {
    const expected = known.get(file.path);
    if (!expected || expected.sha256 !== file.sha256 || expected.bytes !== file.bytes) throw new Error('unknown or unlisted local asset');
    return folder.read(expected, readSignal);
  } };
}
