export interface FileRef { path: string; bytes: number; sha256: string }
const MAX_FILE_BYTES = 64 * 1024 * 1024;

export function assetUrl(base: string, path: string): string {
  if (!path || !/^[a-zA-Z0-9_./-]+$/.test(path) || path.startsWith('/') || path.split('/').some((p) => !p || p === '.' || p === '..')) {
    throw new Error('invalid asset path');
  }
  return new URL(path, base).href;
}

function checkRef(file: FileRef) {
  if (!Number.isSafeInteger(file.bytes) || file.bytes <= 0 || file.bytes > MAX_FILE_BYTES || !/^[0-9a-f]{64}$/.test(file.sha256)) {
    throw new Error('invalid asset size or hash');
  }
}

async function verify(data: Uint8Array<ArrayBuffer>, file: FileRef) {
  checkRef(file);
  if (data.byteLength !== file.bytes) throw new Error('asset byte length mismatch');
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map((n) => n.toString(16).padStart(2, '0')).join('');
  if (hash !== file.sha256) throw new Error('asset hash mismatch');
  return data;
}

export async function fetchVerified(url: string, file: FileRef, signal?: AbortSignal, fetcher: typeof fetch = fetch): Promise<Uint8Array<ArrayBuffer>> {
  checkRef(file);
  const response = await fetcher(url, { signal, cache: 'force-cache' });
  if (!response.ok || !response.body) throw new Error(`asset download failed: ${response.status}`);
  const declared = response.headers.get('content-length');
  const encoding = response.headers.get('content-encoding');
  if ((!encoding || encoding === 'identity') && declared !== null && Number(declared) !== file.bytes) throw new Error('asset content length mismatch');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > file.bytes) { await reader.cancel(); throw new Error('asset exceeds declared size'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  if (size !== file.bytes) throw new Error('asset byte length mismatch');
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return verify(bytes, file);
}

export async function joinVerifiedParts(parts: readonly Uint8Array[], file: FileRef): Promise<Uint8Array<ArrayBuffer>> {
  checkRef(file);
  if (parts.reduce((size, p) => size + p.byteLength, 0) !== file.bytes) throw new Error('asset parts byte length mismatch');
  const bytes = new Uint8Array(file.bytes);
  let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
  return verify(bytes, file);
}
