import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { preparePublicRuntime } from '../prepare-public-runtime.mjs';

const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
function fixture() {
  const work=mkdtempSync(join(tmpdir(),'voxelshogi-runtime-copy-')),runtime=join(work,'runtime'),output=join(work,'output');
  mkdirSync(join(runtime,'dist'),{recursive:true});writeFileSync(join(runtime,'package.json'),JSON.stringify({version:'1.31.1'}));
  const prefix=`runtime/${'a'.repeat(64)}/`;
  const ref=(name,bytes)=>({path:prefix+name,bytes:bytes.length,sha256:digest(bytes)});
  const bodies={'ort.webgpu.bundle.min.mjs':'bundle','ort-wasm-simd-threaded.asyncify.mjs':'bootstrap','ort-wasm-simd-threaded.asyncify.wasm':'abcde'};
  for(const [name,body]of Object.entries(bodies))writeFileSync(join(runtime,'dist',name),body);
  for(const name of ['LICENSE','ThirdPartyNotices.txt'])writeFileSync(join(runtime,name),name);
  const index={schema:1,runtime:{version:'1.31.1',bundle:ref('ort.webgpu.bundle.min.mjs','bundle'),bootstrap:ref('ort-wasm-simd-threaded.asyncify.mjs','bootstrap'),
    wasm:{bytes:5,sha256:digest('abcde'),parts:[ref('part-000.bin','ab'),ref('part-001.bin','cde')]},notices:[ref('LICENSE','LICENSE'),ref('ThirdPartyNotices.txt','ThirdPartyNotices.txt')]}};
  return{work,runtime,output,index};
}
test('copies exact locally pinned bytes and complete WASM parts without any network or models',()=>{
  const f=fixture();try{
    preparePublicRuntime(f.index,f.runtime,f.runtime,f.output);
    const parts=f.index.runtime.wasm.parts.map(ref=>readFileSync(join(f.output,ref.path)));
    assert.equal(Buffer.concat(parts).toString(),'abcde');
    assert.equal(readFileSync(join(f.output,f.index.runtime.bundle.path),'utf8'),'bundle');
    assert.deepEqual(JSON.parse(readFileSync(join(f.output,'index.json'))),f.index);
  }finally{rmSync(f.work,{recursive:true,force:true});}
});
test('rejects corrupted installed bytes and unsafe paths instead of trusting a remote response',()=>{
  for(const mutate of [f=>writeFileSync(join(f.runtime,'dist','ort.webgpu.bundle.min.mjs'),'broken'),f=>{f.index.runtime.bundle.path='../escape'}]){
    const f=fixture();try{mutate(f);assert.throws(()=>preparePublicRuntime(f.index,f.runtime,f.runtime,f.output));}finally{rmSync(f.work,{recursive:true,force:true});}
  }
});
