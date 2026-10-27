import { expect, it } from 'vitest';
import { profileNode } from '../src/inference/profile';

it('extracts placement from the pinned ORT native profiler rather than treating a requested EP as evidence', () => {
  expect(profileNode('{"cat":"Node","args":{"provider":"WebGpuExecutionProvider","op_name":"MatMul"}},')).toEqual({ provider: 'WebGpuExecutionProvider', operator: 'MatMul' });
  expect(profileNode('{"cat":"Node","args":{"provider":"CPUExecutionProvider","op_name":"LayerNormalization"}}')).toEqual({ provider: 'CPUExecutionProvider', operator: 'LayerNormalization' });
  for (const text of ['[', ']', 'not json', '{"cat":"Session"}', '{"cat":"Node","args":{}}']) expect(profileNode(text)).toBeNull();
});
