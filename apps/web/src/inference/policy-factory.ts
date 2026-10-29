import init, { Game } from '../wasm/pkg/voxelshogi_wasm.js';
import wasmUrl from '../wasm/pkg/voxelshogi_wasm_bg.wasm?url';
import { openBackend } from './backend';
import { loadLocalModel, parseTrainedCatalog, readTrainedCatalog } from './local-model';
import { localFile, type ModelFile, type PolicyPhase } from './policy-protocol';
import { PolicySession, parsePolicySelection, type PolicyDependencies, type PolicySelection } from './policy-session';
import { loadRuntimeIndex } from './runtime';
import type { PolicyRuntime } from './policy-host';

interface FactoryDependencies {
  origin: string;
  catalog: (url: string) => Promise<unknown>;
  model: typeof loadLocalModel;
  index: typeof loadRuntimeIndex;
  init: () => Promise<void>;
  make: (deps: PolicyDependencies) => Pick<PolicySession, 'initialize' | 'bestMove' | 'dispose'>;
}
export { readTrainedCatalog } from './local-model';

/** Called inside the dedicated Worker. The request cannot override catalog or runtime URLs. */
export async function createPolicyRuntime(files: ModelFile[], value: PolicySelection, phase: (value: PolicyPhase) => void = () => {}, overrides: Partial<FactoryDependencies> = {}): Promise<PolicyRuntime> {
  const deps: FactoryDependencies = {
    origin: overrides.origin ?? self.location.origin,
    catalog: readTrainedCatalog, model: loadLocalModel, index: loadRuntimeIndex,
    init: async () => { await init({ module_or_path: wasmUrl }); },
    make: params => new PolicySession(params), ...overrides,
  };
  const selection = parsePolicySelection(value);
  const catalog = parseTrainedCatalog(await deps.catalog(new URL('/models/m6/catalog.json', deps.origin).href));
  const release = catalog.find(item => item.id === selection.modelId && item.manifest.sha256 === selection.packageHash);
  if (!release) throw new Error('selected model is not an approved catalog release');
  const source = await deps.model(files.map(localFile), release);
  const runtime = await deps.index(new URL('/models/m3/index.json', deps.origin).href);
  await deps.init();
  phase('validating');
  const session = deps.make({ source, open: (backend, precision) => openBackend(runtime, backend, precision), game: json => Game.fromRecordJson(json), now: () => performance.now() });
  try { return { session, validation: await session.initialize(selection) }; }
  catch (error) { await session.dispose(); throw error; }
}
