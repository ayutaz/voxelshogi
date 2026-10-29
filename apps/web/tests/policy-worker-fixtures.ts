import type { PolicyRequest } from '../src/inference/policy-protocol';

export function policyRequest(withFiles = true): PolicyRequest {
  return { schema: 1, kind: 'policy', requestId: 1,
    selection: { modelId: 'voxelshogi-transformer-s-m6-314159-v1', packageHash: 'a'.repeat(64), precision: 'fp32', backend: 'wasm' },
    root: { revision: 7, cursor: 0, side: 'b', hash: '1'.repeat(16), ruleset: 'voxelshogi-standard-v1', recordJson: '{}' },
    ...(withFiles ? { files: [{ path: 'download/manifest.json', file: new File(['{}'], 'manifest.json') }] } : {}) };
}
export function policyResult(request = policyRequest()) {
  const { recordJson: _record, ...root } = request.root;
  void _record;
  const comparison = (elements: number) => ({ elements, maxAbs: 0, maxRelative: 0, exceeded: 0, atol: request.selection.precision === 'fp16' ? 1e-3 : 1e-5, rtol: request.selection.precision === 'fp16' ? 1e-2 : 1e-4 });
  return { schema: 1, kind: 'result', requestId: request.requestId,
    result: { root, selection: { ...request.selection }, finished: false, inferenceMs: 1,
      choice: { move: '111211', action: 2, rawAction: 0, rawLegal: false, value: .25 } },
    validation: { selection: { ...request.selection }, fixtures: ['initial-b', 'after-one-w'].map(name => ({ name, comparison: { policy: comparison(1067985), value: comparison(1) } })),
      information: { backend: request.selection.backend, adapter: null, features: [] as string[], runtimeBytes: 100 },
      profile: { providers: { CPUExecutionProvider: 1 }, operators: { MatMul: 1 } } } };
}
