import { indexLocalFolder, type LocalFile } from './local-model';
import { POLICY_ELEMENTS } from './manifest';
import { outputTolerances, TRAINED_NUMERIC_CONTRACT } from './numeric';
import { policyAction } from './policy-contract';
import { parsePolicyPosition, parsePolicySelection, type PolicyPosition, type PolicyRoot, type PolicySelection, type PolicyReply, type PolicyValidation } from './policy-session';

export interface ModelFile { path: string; file: File }
export interface PolicyRequest { schema: 1; kind: 'policy'; requestId: number; selection: PolicySelection; root: PolicyPosition; files?: ModelFile[] }
export type PolicyPhase = 'loading' | 'validating' | 'running';
interface Identity { schema: 1; requestId: number; selection: PolicySelection; root: PolicyRoot }
export interface PolicyProgress extends Identity { kind: 'progress'; phase: PolicyPhase }
export interface PolicyFailure extends Omit<Identity, 'selection' | 'root'> { kind: 'error'; selection: PolicySelection | null; root: PolicyRoot | null; code: 'input' | 'busy' | 'initialization' | 'inference'; message: string }
export interface PolicySuccess { schema: 1; kind: 'result'; requestId: number; result: PolicyReply; validation: PolicyValidation }
export type PolicyResponse = PolicyProgress | PolicyFailure | PolicySuccess;
const selectionKeys = ['modelId', 'packageHash', 'precision', 'backend'] as const;
const rootKeys = ['revision', 'cursor', 'side', 'hash', 'ruleset'] as const;

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid policy protocol object');
  return value as Record<string, unknown>;
}
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const integer = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= maximum;
export function samePolicySelection(first: PolicySelection, second: PolicySelection): boolean { return selectionKeys.every(key => first[key] === second[key]); }
export function policyRoot(position: PolicyPosition): PolicyRoot {
  return { revision: position.revision, cursor: position.cursor, side: position.side, hash: position.hash, ruleset: position.ruleset };
}
export function localFile(entry: ModelFile): LocalFile {
  return { name: entry.file.name, webkitRelativePath: entry.path, size: entry.file.size, arrayBuffer: () => entry.file.arrayBuffer() };
}
function parseFiles(value: unknown): ModelFile[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 512) throw new Error('invalid transferred model files');
  const files = value.map(item => {
    const entry = record(item);
    if (Object.keys(entry).length !== 2 || typeof entry.path !== 'string' || !(entry.file instanceof File) || entry.file.name !== entry.path.split('/').at(-1)) throw new Error('invalid transferred model file/path');
    return { path: entry.path, file: entry.file };
  });
  indexLocalFolder(files.map(localFile)); // Metadata only; no arrayBuffer calls.
  return files;
}
/** Explicit relative paths survive even where File's nonstandard path property is not cloned. */
export function packModelFiles(files: readonly File[]): ModelFile[] {
  return parseFiles(files.map(file => ({ path: file.webkitRelativePath, file })));
}
export function parsePolicyRequest(value: unknown): PolicyRequest {
  const request = record(value), keys = ['schema', 'kind', 'requestId', 'selection', 'root', 'files'];
  if (Object.keys(request).some(key => !keys.includes(key)) || request.schema !== 1 || request.kind !== 'policy' || !integer(request.requestId) || request.requestId < 1) throw new Error('invalid policy request envelope');
  return { schema: 1, kind: 'policy', requestId: request.requestId, selection: parsePolicySelection(request.selection), root: parsePolicyPosition(request.root),
    ...(request.files === undefined ? {} : { files: parseFiles(request.files) }) };
}

function identity(value: unknown, request: PolicyRequest) {
  const object = record(value), root = record(object.root), selected = parsePolicySelection(object.selection);
  if (Object.keys(root).length !== 5 || rootKeys.some(key => root[key] !== request.root[key]) || !samePolicySelection(selected, request.selection)) throw new Error('policy reply root/model mismatch');
}
function validation(value: unknown, request: PolicyRequest, expectedFixtures: readonly string[], expectedWeightOnly: boolean) {
  const result = record(value), selected = parsePolicySelection(result.selection);
  if (!samePolicySelection(selected, request.selection) || !Array.isArray(result.fixtures) || result.fixtures.length !== expectedFixtures.length || result.fixtures.length < 1 || result.fixtures.length > 32) throw new Error('policy validation fixture/model mismatch');
  const names = new Set<string>();
  for (const item of result.fixtures) {
    const fixture = record(item), comparison = record(fixture.comparison);
    if (typeof fixture.name !== 'string' || !expectedFixtures.includes(fixture.name) || names.has(fixture.name)) throw new Error('incomplete/duplicate policy reference fixtures');
    names.add(fixture.name);
    for (const name of ['policy', 'value'] as const) {
      const [atol, rtol] = outputTolerances(selected.precision, name, TRAINED_NUMERIC_CONTRACT);
      const stats = record(comparison[name]);
      if (stats.elements !== (name === 'policy' ? POLICY_ELEMENTS : 1) || stats.exceeded !== 0 || stats.atol !== atol || stats.rtol !== rtol || !finite(stats.maxAbs) || !finite(stats.maxRelative)) throw new Error('invalid same-format policy numeric comparison');
    }
  }
  const info = record(result.information), profile = record(result.profile), providers = Object.entries(record(profile.providers));
  if ((result.fp16WeightOnly ?? false) !== expectedWeightOnly || (expectedWeightOnly && (selected.precision !== 'fp16' || info.computePrecision !== 'float32'))) throw new Error('unexpected policy compute precision');
  const expected = selected.backend === 'webgpu' ? 'WebGpuExecutionProvider' : 'CPUExecutionProvider';
  if (info.backend !== selected.backend || !integer(info.runtimeBytes) || info.runtimeBytes === 0 || !Array.isArray(info.features) || info.features.length > 64 || info.features.some(feature => typeof feature !== 'string' || feature.length > 64) ||
    providers.length !== 1 || providers.some(([name, count]) => name !== expected || !integer(count) || count < 1)) throw new Error('unverified policy backend placement');
  const operators = Object.entries(record(profile.operators));
  if (operators.length === 0 || operators.some(([name, count]) => !name || !integer(count) || count < 1)) throw new Error('missing policy operator evidence');
  if (selected.backend === 'webgpu') {
    const adapter = record(info.adapter);
    if (['vendor', 'architecture', 'device', 'description'].some(key => typeof adapter[key] !== 'string' || adapter[key].length > 1024) || (selected.precision === 'fp16' && !expectedWeightOnly && !info.features.includes('shader-f16'))) throw new Error('invalid policy adapter information');
  } else if (info.adapter !== null) throw new Error('unexpected adapter for WASM backend');
}

export function parsePolicyResponse(value: unknown, request: PolicyRequest, expectedFixtures: readonly string[], expectedWeightOnly = false): PolicyResponse {
  const message = record(value);
  if (message.schema !== 1 || message.requestId !== request.requestId) throw new Error('policy response ID/schema mismatch');
  identity(message.kind === 'result' ? message.result : message, request);
  if (message.kind === 'progress') {
    if (!['loading', 'validating', 'running'].includes(String(message.phase))) throw new Error('invalid policy progress');
  } else if (message.kind === 'error') {
    if (!['input', 'busy', 'initialization', 'inference'].includes(String(message.code)) || typeof message.message !== 'string' || message.message.length < 1 || message.message.length > 500) throw new Error('invalid policy error');
  } else if (message.kind === 'result') {
    validation(message.validation, request, expectedFixtures, expectedWeightOnly);
    const result = record(message.result);
    if (typeof result.finished !== 'boolean' || !finite(result.inferenceMs) || (result.finished && (result.choice !== null || result.inferenceMs !== 0))) throw new Error('invalid policy terminal/timing result');
    if (!result.finished) {
      const choice = record(result.choice);
      if (typeof choice.move !== 'string' || !integer(choice.action, POLICY_ELEMENTS - 1) || choice.action !== policyAction(choice.move, request.root.side) || !integer(choice.rawAction, POLICY_ELEMENTS - 1) || typeof choice.rawLegal !== 'boolean' || choice.rawLegal !== (choice.rawAction === choice.action) || typeof choice.value !== 'number' || !Number.isFinite(choice.value) || Math.abs(choice.value) > 1) throw new Error('invalid canonical policy choice');
    }
  } else throw new Error('unknown policy response');
  return value as PolicyResponse;
}
