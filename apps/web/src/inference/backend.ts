import { loadRuntime, type RuntimeIndex } from './runtime';
import { type Backend, type Precision, POLICY_ELEMENTS } from './manifest';
import { profileNode } from './profile';
import { inferenceOptions } from './options';

export interface OutputData { policy: Float32Array; value: Float32Array; dispose: () => void }
export interface SessionPort { run: (features: Float32Array) => Promise<OutputData>; finishProfiling?: () => Promise<void>; release: () => Promise<void> }
export interface Profile { providers: Record<string, number>; operators: Record<string, number> }
export interface RuntimeInfo {
  backend: string; adapter: { vendor: string; architecture: string; device: string; description: string } | null;
  features: string[]; runtimeBytes: number;
}
export interface BackendPort {
  createSession: (model: Uint8Array<ArrayBuffer>, precision: Precision) => Promise<SessionPort>;
  profile: () => Profile; resetProfile: () => void; dispose: () => Promise<void>;
  info: RuntimeInfo; buffers?: () => { created: number; liveBytes: number; peakBytes: number } | null;
}

export async function openBackend(pkg: RuntimeIndex, backend: Backend, precision: Precision): Promise<BackendPort> {
  let device: GPUDevice | undefined;
  let adapterInfo: RuntimeInfo['adapter'] = null;
  const features: GPUFeatureName[] = [];
  const buffers = { created: 0, liveBytes: 0, peakBytes: 0 };
  if (backend === 'webgpu') {
    if (!navigator.gpu) throw new Error('WebGPU is not available');
    const adapter = await navigator.gpu.requestAdapter();
    if (!adapter) throw new Error('WebGPU adapter is not available');
    if (precision === 'fp16' && !adapter.features.has('shader-f16')) throw new Error('shader-f16 is not available');
    for (const name of ['shader-f16', 'timestamp-query'] as const) if (adapter.features.has(name)) features.push(name);
    device = await adapter.requestDevice({ requiredFeatures: features });
    const info = adapter.info;
    adapterInfo = { vendor: info.vendor, architecture: info.architecture, device: info.device, description: info.description };
    const create = device.createBuffer.bind(device);
    device.createBuffer = (descriptor) => {
      const buffer = create(descriptor);
      buffers.created++; buffers.liveBytes += buffer.size; buffers.peakBytes = Math.max(buffers.peakBytes, buffers.liveBytes);
      const destroy = buffer.destroy.bind(buffer);
      let live = true;
      buffer.destroy = () => { if (live) { buffers.liveBytes -= buffer.size; live = false; } destroy(); };
      return buffer;
    };
  }
  let evidence: Profile = { providers: {}, operators: {} };
  const originalLog = console.log;
  console.log = (...args: unknown[]) => {
    const node = typeof args[0] === 'string' ? profileNode(args[0]) : null;
    if (node) {
      evidence.providers[node.provider] = (evidence.providers[node.provider] ?? 0) + 1;
      evidence.operators[node.operator] = (evidence.operators[node.operator] ?? 0) + 1;
    } else if (!(args.length === 1 && typeof args[0] === 'string' && ['[', ']', ','].includes(args[0].trim()))) originalLog(...args);
  };
  try {
    const loaded = await loadRuntime(pkg.assetBase, pkg.index.runtime);
    const { ort } = loaded;
    if (device) ort.env.webgpu.device = device;
    return {
      info: { backend, adapter: adapterInfo, features, runtimeBytes: loaded.runtimeBytes },
      buffers: () => backend === 'webgpu' && buffers.created === 0 ? null : { ...buffers }, profile: () => structuredClone(evidence), resetProfile: () => { evidence = { providers: {}, operators: {} }; },
      dispose: async () => { loaded.dispose(); device?.destroy(); console.log = originalLog; },
      createSession: async (model, sessionPrecision) => {
        const session = await ort.InferenceSession.create(model, inferenceOptions(backend, sessionPrecision));
        ort.env.wasm.wasmBinary = undefined;
        return {
          release: () => session.release(),
          finishProfiling: async () => { session.endProfiling(); await Promise.resolve(); },
          run: async (features) => {
            const input = new ort.Tensor('float32', features, [1, 729, 43]);
            let outputs: Awaited<ReturnType<typeof session.run>> | undefined;
            try {
              outputs = await session.run({ features: input });
              const policy = outputs.policy!, value = outputs.value!;
              if (policy.type !== 'float32' || value.type !== 'float32' || policy.dims.join(',') !== `1,${POLICY_ELEMENTS}` || value.dims.join(',') !== '1,1') throw new Error('model output shape/dtype mismatch');
              const policyData = await policy.getData(), valueData = await value.getData();
              if (!(policyData instanceof Float32Array) || !(valueData instanceof Float32Array)) throw new Error('invalid model output data');
              await device?.queue.onSubmittedWorkDone();
              const tensors = outputs;
              return { policy: policyData, value: valueData, dispose: () => { input.dispose(); Object.values(tensors).forEach((t) => t.dispose()); } };
            } catch (error) {
              input.dispose(); if (outputs) Object.values(outputs).forEach((t) => t.dispose());
              throw error;
            }
          },
        };
      },
    };
  } catch (error) { device?.destroy(); console.log = originalLog; throw error; }
}
