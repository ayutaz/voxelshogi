import type { Backend, Precision } from './manifest';
import type { Ort } from './runtime';

export function inferenceOptions(backend: Backend, precision: Precision): NonNullable<Parameters<Ort['InferenceSession']['create']>[1]> {
  return { executionProviders: [backend], graphOptimizationLevel: precision === 'int8' ? 'basic' : 'all', enableProfiling: true, logSeverityLevel: 2,
    extra: { session: { disable_cpu_ep_fallback: backend === 'webgpu' ? '1' : '0' } } };
}
