import { expect, it } from 'vitest';
import { parseTrainedModel } from '../src/inference/manifest';
import { parsePolicyResponse } from '../src/inference/policy-protocol';
import { trainedFixture, releaseFixture } from './local-model-fixtures';
import { policyRequest, policyResult } from './policy-worker-fixtures';

it('accepts explicit export/training lineage and rejects either source being relabeled', () => {
  const m = trainedFixture(), identity = releaseFixture();
  m.training.binding.source_commit = 'a'.repeat(40);
  Reflect.set(m.training, 'export_provenance', { schema: 'voxelshogi-export-lineage-v1', training_source_commit: 'a'.repeat(40), export_source_commit: identity.sourceCommit });
  expect(() => parseTrainedModel(m, identity)).not.toThrow();
  for (const field of ['schema', 'training_source_commit', 'export_source_commit']) {
    const bad = structuredClone(m); Reflect.set(Reflect.get(bad.training, 'export_provenance'), field, 'bad');
    expect(() => parseTrainedModel(bad, identity)).toThrow();
  }
});

it('requires the independently expected weight-only mode before accepting FP16 without shader-f16', () => {
  const request = policyRequest(); request.selection.backend = 'webgpu'; request.selection.precision = 'fp16';
  const result = policyResult(request);
  Reflect.set(result.validation, 'fp16WeightOnly', true);
  Reflect.set(result.validation.information, 'computePrecision', 'float32');
  Reflect.set(result.validation.information, 'adapter', { vendor: 'fake', architecture: 'fake', device: '', description: '' });
  Reflect.set(result.validation.profile, 'providers', { WebGpuExecutionProvider: 1 });
  expect(() => parsePolicyResponse(result, request, ['initial-b', 'after-one-w'])).toThrow();
  expect(() => parsePolicyResponse(result, request, ['initial-b', 'after-one-w'], true)).not.toThrow();
  Reflect.set(result.validation.information, 'computePrecision', 'float16');
  expect(() => parsePolicyResponse(result, request, ['initial-b', 'after-one-w'], true)).toThrow();
});

it('does not accept an unsolicited storage-only claim even for a WASM result', () => {
  const request=policyRequest(); request.selection.precision='fp16'; const result=policyResult(request);
  Reflect.set(result.validation,'fp16WeightOnly',true); Reflect.set(result.validation.information,'computePrecision','float32');
  expect(()=>parsePolicyResponse(result,request,['initial-b','after-one-w'])).toThrow(/compute precision/);
});

it('validates the advertised FP16 storage and FP32 activation contract', () => {
  const m=trainedFixture(),v=m.variants[0]!;Object.assign(v,{id:'fp16',precision:'fp16',conversion:{method:'fp16-weight-only',compute:'float32',activations:'float32',convertedTensors:1,convertedElements:6},fp32Difference:{'initial-b':{policy:{elements:1067985,maxAbs:0,mae:0,rmse:0,maxRelative:0,argmaxEqual:true},value:{elements:1,maxAbs:0,mae:0,rmse:0,maxRelative:0,argmaxEqual:true}}}});
  expect(()=>parseTrainedModel(m,releaseFixture())).not.toThrow();
  Reflect.set(Reflect.get(v,'conversion'),'compute','float16');expect(()=>parseTrainedModel(m,releaseFixture())).toThrow(/conversion/);
});
