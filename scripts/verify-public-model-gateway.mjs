import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

assert.equal(process.platform,'linux');
const root=fileURLToPath(new URL('../',import.meta.url));
const revision='6ab524574d36536348dbe323a2b779b9cebe37ed';
const publicSite=process.argv.includes('--public');
const release=JSON.parse(readFileSync(join(root,'apps/web/public/models/m6/catalog.json'))).releases.find(r=>r.publicDownload===true);
assert.equal(release.revision,revision);
const files=[release.manifest,...release.notices],verified=[];
const server=publicSite?null:spawn('bash',[join(root,'scripts/cf.sh'),'dev','--local','--ip','127.0.0.1','--port','4175'],{cwd:root,detached:true,stdio:'ignore',env:{...process.env,CI:'true',WRANGLER_SEND_METRICS:'false'}});
try{
  let ready=publicSite;
  if(!publicSite){
  for(let attempt=0;attempt<60;attempt++){
    if(server.exitCode!==null)throw Error('local Worker exited');
    try{const response=await fetch('http://127.0.0.1:4175/build-info.json',{signal:AbortSignal.timeout(1000)});if(response.ok){ready=true;break}}catch{/* finite local startup readiness */}
    await delay(250);
  }
  }
  assert.ok(ready,'local Worker did not start');
  for(const path of ['manifest.json','README.md','LICENSE']){
    const expected=files.find(f=>f.path===path);assert.ok(expected&&expected.bytes<=1024*1024);
    const base=publicSite?'https://voxelshogi.yousan-apps.workers.dev':'http://127.0.0.1:4175';
    const response=await fetch(`${base}/api/models/s/${revision}/${path}`,{credentials:'omit'});assert.equal(response.status,200,path);
    const bytes=Buffer.from(await response.arrayBuffer());assert.equal(bytes.length,expected.bytes,path);assert.equal(createHash('sha256').update(bytes).digest('hex'),expected.sha256,path);
    verified.push(expected);
  }
  const proof={schema:1,kind:publicSite?'public-s-deployed-gateway':'public-s-local-worker-gateway',revision,anonymous:true,files:verified,verified:true,gameWrites:0};
  if(process.argv[2])writeFileSync(process.argv[2],JSON.stringify(proof,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log(JSON.stringify(proof));
}finally{if(server?.pid&&server.exitCode===null){try{process.kill(-server.pid,'SIGTERM')}catch{/* already exited */}}}
