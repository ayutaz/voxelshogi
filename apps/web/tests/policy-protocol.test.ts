import { expect, it, vi } from 'vitest';
import { parsePolicyRequest, parsePolicyResponse, packModelFiles } from '../src/inference/policy-protocol';
import { policyRequest, policyResult } from './policy-worker-fixtures';

const fixtures = ['initial-b', 'after-one-w'];
it('carries explicit paths alongside cloneable File objects without reading their bodies', () => {
  const file = new File(['{}'], 'manifest.json'), read = vi.spyOn(file, 'arrayBuffer');
  Object.defineProperty(file, 'webkitRelativePath', { value: 'download/manifest.json' });
  const entries = packModelFiles([file]);
  expect(entries[0]!.path).toBe('download/manifest.json'); expect(entries[0]!.file).toBe(file);
  const request = policyRequest(); request.files = entries;
  expect(parsePolicyRequest(request).files![0]!.file).toBe(file);
  expect(read).not.toHaveBeenCalled();
  // File serialization does not promise the nonstandard webkitRelativePath field.
  const separateFile = new File(['{}'], 'manifest.json');
  expect(parsePolicyRequest({ ...request, files: [{ path: entries[0]!.path, file: separateFile }] }).files![0]!.path).toBe('download/manifest.json');
});

for (const change of [{ requestId: 0 }, { requestId: 1.5 }, { kind: 'other' }, { schema: 2 }, { extra: true }, { files: [] }]) {
  it(`rejects malformed request metadata ${JSON.stringify(change)}`, () => expect(() => parsePolicyRequest({ ...policyRequest(), ...change })).toThrow());
}
it('rejects non-file data, traversal, duplicate paths and mismatched file names', () => {
  for (const files of [[{ path: 'download/manifest.json', file: {} }], [{ path: '../manifest.json', file: new File(['{}'], 'manifest.json') }],
    [{ path: 'download/manifest.json', file: new File(['{}'], 'other.json') }], [...policyRequest().files!, ...policyRequest().files!]])
    expect(() => parsePolicyRequest({ ...policyRequest(), files })).toThrow();
  expect(parsePolicyRequest(policyRequest(false)).files).toBeUndefined();
});

it('validates a result against the exact turn, model, backend and complete reference set', () => {
  const request = policyRequest(), result = policyResult(request);
  expect(parsePolicyResponse(result, request, fixtures).kind).toBe('result');
});

it('accepts explicitly evidenced FP16 WebGPU and rejects missing f16 support', () => {
  const request = policyRequest(); request.selection.backend = 'webgpu'; request.selection.precision = 'fp16';
  const result = policyResult(request);
  Reflect.set(result.validation.information, 'adapter', { vendor: 'fixture', architecture: 'fixture', device: '', description: 'not physical GPU evidence' });
  result.validation.information.features.push('shader-f16');
  Reflect.set(result.validation.profile, 'providers', { WebGpuExecutionProvider: 1 });
  expect(parsePolicyResponse(result, request, fixtures).kind).toBe('result');
  result.validation.information.features = [];
  expect(() => parsePolicyResponse(result, request, fixtures)).toThrow(/adapter/);
});

for (const field of ['id', 'revision', 'cursor', 'hash', 'side', 'model', 'precision', 'package', 'backend', 'policy-elements', 'value-elements', 'exceeded', 'tolerance', 'missing-fixture', 'duplicate-fixture', 'provider', 'value', 'action', 'raw-legal', 'timing', 'terminal']) {
  it(`rejects an invalid or stale policy reply: ${field}`, () => {
    const request = policyRequest(), result = policyResult(request);
    if (field === 'id') result.requestId = 2;
    if (field === 'revision') result.result.root.revision++;
    if (field === 'cursor') result.result.root.cursor++;
    if (field === 'hash') result.result.root.hash = '2'.repeat(16);
    if (field === 'side') result.result.root.side = 'w';
    if (field === 'model') result.result.selection.modelId = 'other';
    if (field === 'precision') result.result.selection.precision = 'int8';
    if (field === 'package') result.result.selection.packageHash = 'b'.repeat(64);
    if (field === 'backend') result.validation.information.backend = 'webgpu';
    if (field === 'policy-elements') result.validation.fixtures[0]!.comparison.policy.elements--;
    if (field === 'value-elements') result.validation.fixtures[0]!.comparison.value.elements++;
    if (field === 'exceeded') result.validation.fixtures[0]!.comparison.policy.exceeded = 1;
    if (field === 'tolerance') result.validation.fixtures[0]!.comparison.policy.atol = 10;
    if (field === 'missing-fixture') result.validation.fixtures.pop();
    if (field === 'duplicate-fixture') result.validation.fixtures[1] = result.validation.fixtures[0]!;
    if (field === 'provider') result.validation.profile.providers.CPUExecutionProvider = 0;
    if (field === 'value') result.result.choice.value = NaN;
    if (field === 'action') result.result.choice.action = 3;
    if (field === 'raw-legal') result.result.choice.rawLegal = true;
    if (field === 'timing') result.result.inferenceMs = -1;
    if (field === 'terminal') result.result.finished = true;
    expect(() => parsePolicyResponse(result, request, fixtures)).toThrow();
  });
}

it('rejects a policy reply that widens the Value bound to the Policy bound', () => {
  const request = policyRequest(), result = policyResult(request);
  result.validation.fixtures[0]!.comparison.value.atol = .0001;
  expect(() => parsePolicyResponse(result, request, fixtures)).toThrow(/numeric/);
});

it('checks root identity on progress/error messages as well as results', () => {
  const request = policyRequest(), { recordJson: _record, ...root } = request.root;
  void _record;
  const progress = { schema: 1, kind: 'progress', requestId: request.requestId, selection: request.selection, root, phase: 'validating' };
  expect(parsePolicyResponse(progress, request, fixtures)).toMatchObject({ kind: 'progress', phase: 'validating' });
  expect(() => parsePolicyResponse({ ...progress, phase: 'other' }, request, fixtures)).toThrow();
  const error = { ...progress, kind: 'error', code: 'initialization', message: 'model validation failed' };
  expect(parsePolicyResponse(error, request, fixtures)).toMatchObject({ kind: 'error', code: 'initialization' });
  expect(() => parsePolicyResponse({ ...error, root: { ...root, revision: 8 } }, request, fixtures)).toThrow();
});
