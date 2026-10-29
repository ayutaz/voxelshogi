import { afterEach, expect, it, vi } from 'vitest';
import { createPolicyRuntime, readTrainedCatalog } from '../src/inference/policy-factory';
import { parseTrainedCatalog, type LocalModel } from '../src/inference/local-model';
import { parseTrainedModel, parseDeployment } from '../src/inference/manifest';
import type { PolicyDependencies } from '../src/inference/policy-session';
import { loadRuntimeIndex } from '../src/inference/runtime';
import { deploymentFixture } from './inference-fixtures';
import { releaseFixture, trainedFixture } from './local-model-fixtures';
import { policyRequest, policyResult } from './policy-worker-fixtures';

vi.mock('../src/wasm/pkg/voxelshogi_wasm.js', () => ({ default: vi.fn(), Game: { fromRecordJson: vi.fn() } }));
afterEach(() => vi.unstubAllGlobals());

function setup() {
  const release = parseTrainedCatalog({ schema: 1, releases: [releaseFixture()] })[0]!;
  const selection = { ...policyRequest().selection, packageHash: release.manifest.sha256 };
  const source: LocalModel = { release, model: parseTrainedModel(trainedFixture(), release), packageHash: selection.packageHash, read: vi.fn(async () => { throw new Error('no model execution in this factory test'); }) };
  const request = { ...policyRequest(), selection };
  const session = { initialize: vi.fn(async () => policyResult(request).validation), bestMove: vi.fn(async () => policyResult(request).result), dispose: vi.fn(async () => {}) };
  const dependencies = {
    origin: 'https://demo.example', catalog: vi.fn<(url: string) => Promise<unknown>>(async () => ({ schema: 1, releases: [release] })),
    model: vi.fn(async () => source), index: vi.fn(async () => ({ index: parseDeployment(deploymentFixture()), assetBase: 'https://demo.example/models/m3/' })),
    init: vi.fn(async () => {}), make: vi.fn<(deps: PolicyDependencies) => typeof session>(() => session),
  };
  return { release, selection, source, session, dependencies, files: request.files! };
}

it('uses only the fixed same-origin catalog/runtime paths and the matching approved local release', async () => {
  const f = setup(), phase = vi.fn();
  const ready = await createPolicyRuntime(f.files, f.selection, phase, f.dependencies);
  expect(f.dependencies.catalog).toHaveBeenCalledWith('https://demo.example/models/m6/catalog.json');
  expect(f.dependencies.model).toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ webkitRelativePath: 'download/manifest.json' })]), f.release);
  expect(f.dependencies.index).toHaveBeenCalledWith('https://demo.example/models/m3/index.json');
  expect(f.dependencies.init).toHaveBeenCalledTimes(1);
  expect(f.dependencies.make.mock.calls[0]![0].source).toBe(f.source);
  expect(f.session.initialize).toHaveBeenCalledWith(f.selection);
  expect(phase).toHaveBeenCalledWith('validating'); expect(ready.session).toBe(f.session);
  expect(f.source.read).not.toHaveBeenCalled();
});

it('rejects an absent, unapproved or different-hash catalog entry before local reads and GPU allocation', async () => {
  for (const field of ['missing', 'approval', 'hash']) {
    const f = setup();
    const release = releaseFixture();
    if (field === 'approval') release.approved = false;
    if (field === 'hash') release.manifest.sha256 = 'b'.repeat(64);
    f.dependencies.catalog.mockResolvedValueOnce({ schema: 1, releases: field === 'missing' ? [] : [release] });
    await expect(createPolicyRuntime(f.files, f.selection, vi.fn(), f.dependencies)).rejects.toThrow();
    expect(f.dependencies.model).not.toHaveBeenCalled(); expect(f.dependencies.index).not.toHaveBeenCalled(); expect(f.dependencies.make).not.toHaveBeenCalled();
  }
});

it('disposes a session whose numeric initialization fails', async () => {
  const f = setup(); f.session.initialize.mockRejectedValueOnce(new Error('numeric mismatch'));
  await expect(createPolicyRuntime(f.files, f.selection, vi.fn(), f.dependencies)).rejects.toThrow('numeric mismatch');
  expect(f.session.dispose).toHaveBeenCalledTimes(1);
});

it('fetches only bounded public catalog JSON without credentials, file bodies or redirects', async () => {
  const fetcher = vi.fn(async () => new Response('{"schema":1,"releases":[]}'));
  expect(await readTrainedCatalog('https://demo.example/models/m6/catalog.json', fetcher)).toEqual({ schema: 1, releases: [] });
  expect(fetcher).toHaveBeenCalledWith('https://demo.example/models/m6/catalog.json', { cache: 'no-store', credentials: 'omit', redirect: 'error' });
  await expect(readTrainedCatalog('https://demo.example/catalog', async () => new Response('', { status: 404 }))).rejects.toThrow(/404/);
  await expect(readTrainedCatalog('https://demo.example/catalog', async () => new Response('invalid JSON'))).rejects.toThrow(/catalog/);
});

it('loads only the runtime index metadata without fetching M3 weights or model notices', async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify(deploymentFixture())));
  vi.stubGlobal('fetch', fetcher);
  const result = await loadRuntimeIndex('https://demo.example/models/m3/index.json');
  expect(result.assetBase).toBe('https://demo.example/models/m3/'); expect(result.index.runtime.version).toBe('1.31.1');
  expect(fetcher).toHaveBeenCalledTimes(1);
});
