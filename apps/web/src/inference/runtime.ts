import { assetUrl, fetchVerified, joinVerifiedParts } from './assets';
import { parseDeployment, parseModel, type Deployment, type ModelManifest, type RuntimeManifest } from './manifest';

export type Ort = typeof import('onnxruntime-web/webgpu');
export interface ModelPackage { index: Deployment; model: ModelManifest; assetBase: string; modelBase: string; packageHash: string }

export async function loadPackage(indexUrl: string, signal?: AbortSignal): Promise<ModelPackage> {
  const response = await fetch(indexUrl, { cache: 'no-store', signal });
  if (!response.ok) throw new Error(`model index download failed: ${response.status}`);
  const text = await response.text();
  if (text.length > 1024 * 1024) throw new Error('oversized model index');
  const allowLocal = ['localhost', '127.0.0.1', '[::1]'].includes(new URL(indexUrl).hostname);
  const index = parseDeployment(JSON.parse(text), allowLocal);
  const assetBase = new URL('.', indexUrl).href;
  const modelUrl = assetUrl(assetBase, index.model.path);
  const bytes = await fetchVerified(modelUrl, index.model, signal);
  const model = parseModel(JSON.parse(new TextDecoder().decode(bytes)), index.publication);
  return { index, model, assetBase, modelBase: new URL('.', modelUrl).href, packageHash: index.model.sha256 };
}

/** Imports the exact verified bytes. No second network fetch of executable JS. */
export async function loadRuntime(assetBase: string, runtime: RuntimeManifest, signal?: AbortSignal) {
  const files = [runtime.bundle, runtime.bootstrap, ...runtime.wasm.parts, ...runtime.notices];
  const verified = await Promise.all(files.map((file) => fetchVerified(assetUrl(assetBase, file.path), file, signal)));
  const wasm = await joinVerifiedParts(verified.slice(2, 2 + runtime.wasm.parts.length), runtime.wasm);
  const bundleUrl = URL.createObjectURL(new Blob([verified[0]!], { type: 'text/javascript' }));
  const bootstrapUrl = URL.createObjectURL(new Blob([verified[1]!], { type: 'text/javascript' }));
  try {
    const ort = await import(/* @vite-ignore */ bundleUrl) as Ort;
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.proxy = false;
    ort.env.wasm.wasmPaths = { mjs: bootstrapUrl };
    ort.env.wasm.wasmBinary = wasm.buffer;
    return { ort, runtimeBytes: files.reduce((n, f) => n + f.bytes, 0), dispose: () => {
      URL.revokeObjectURL(bundleUrl); URL.revokeObjectURL(bootstrapUrl);
    } };
  } catch (error) {
    URL.revokeObjectURL(bundleUrl); URL.revokeObjectURL(bootstrapUrl);
    throw error;
  }
}
