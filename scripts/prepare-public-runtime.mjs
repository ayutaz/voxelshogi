import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');

/** Copy pinned installed runtime bytes, never network responses or model weights. */
export function preparePublicRuntime(index, runtimeDirectory, noticesDirectory, outputDirectory) {
  assert.equal(index.runtime.version, '1.31.1');
  assert.equal(JSON.parse(readFileSync(resolve(runtimeDirectory,'package.json'))).version, '1.31.1');
  const write = (ref, bytes) => {
    assert.match(ref.path, /^runtime\/[0-9a-f]{64}\/[A-Za-z0-9_.-]+$/);
    assert.equal(bytes.length,ref.bytes); assert.equal(digest(bytes),ref.sha256);
    const path=resolve(outputDirectory,ref.path);mkdirSync(dirname(path),{recursive:true});writeFileSync(path,bytes);
  };
  for(const [ref,name]of [[index.runtime.bundle,'ort.webgpu.bundle.min.mjs'],[index.runtime.bootstrap,'ort-wasm-simd-threaded.asyncify.mjs']]) write(ref,readFileSync(resolve(runtimeDirectory,'dist',name)));
  const wasm=readFileSync(resolve(runtimeDirectory,'dist','ort-wasm-simd-threaded.asyncify.wasm'));
  assert.equal(wasm.length,index.runtime.wasm.bytes);assert.equal(digest(wasm),index.runtime.wasm.sha256);
  let offset=0;for(const part of index.runtime.wasm.parts){write(part,wasm.subarray(offset,offset+part.bytes));offset+=part.bytes;}assert.equal(offset,wasm.length);
  for(const name of ['LICENSE','ThirdPartyNotices.txt']) {
    const ref=index.runtime.notices.find(file=>file.path.endsWith('/'+name));assert.ok(ref);
    write(ref,readFileSync(resolve(noticesDirectory,name)));
  }
  mkdirSync(outputDirectory,{recursive:true});writeFileSync(resolve(outputDirectory,'index.json'),JSON.stringify(index,null,2)+'\n');
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  assert.equal(process.platform,'linux');
  const runtime=resolve(root,'apps/web/node_modules/onnxruntime-web');
  const index=JSON.parse(readFileSync(resolve(root,'docs/experiments/m3-public-index.json')));
  preparePublicRuntime(index,runtime,existsSync(resolve(runtime,'LICENSE'))?runtime:resolve(root,'third_party/onnxruntime-1.31.1'),resolve(root,'apps/web/public/models/m3'));
  console.log('Copied and hash-verified the pinned local runtime; no network or model copies');
}
