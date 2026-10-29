import type { Precision } from './manifest';
export const TRAINED_NUMERIC_CONTRACT = 'voxelshogi-trained-numeric-v1';
export function outputTolerances(precision: Precision, output: 'policy' | 'value' = 'policy', contract?: string): readonly [number, number] {
  if (!['fp32', 'fp16', 'int8'].includes(precision) || !['policy', 'value'].includes(output)) throw new Error('unknown numeric precision or output');
  if (contract !== undefined && contract !== TRAINED_NUMERIC_CONTRACT) throw new Error('unknown numeric contract');
  if (contract === TRAINED_NUMERIC_CONTRACT && output === 'policy' && precision !== 'fp16') return [1e-4, 1e-4];
  return precision === 'fp16' ? [1e-3, 1e-2] : [1e-5, 1e-4];
}
