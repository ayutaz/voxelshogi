import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

/** Receipt consistency only; the real script also replays the full record in Rust/WASM. */
export function verifyBrowserStorageFlow(first,last,commit){
  assert.equal(first.httpStatus,201);assert.equal(last.httpStatus,200);
  for(const value of [first,last]){
    const p=value.packet,a=value.ack;
    assert.equal(p.schema,2);assert.equal(p.policy,'automatic-game-v2');assert.equal(p.applicationCommit,commit);
    assert.equal(p.mode,'h-r');assert.equal(p.conditionsScope,'game-start');
    assert.equal(p.selectedAgents.b.kind,'human');assert.equal(p.selectedAgents.w.kind,'easy');
    assert.equal(a.gameId,p.gameId);assert.equal(a.requestId,p.requestId);assert.equal(a.version,p.version);assert.equal(a.status,'received_unverified');
    assert.equal(p.record.ruleset_id,'voxelshogi-standard-v1');
  }
  assert.equal(first.packet.gameId,last.packet.gameId);assert.ok(last.packet.version>first.packet.version);
  assert.deepEqual(first.packet.selectedAgents,last.packet.selectedAgents);
  assert.equal(first.packet.record.initial,last.packet.record.initial);
  assert.equal(first.packet.state,'progress');assert.deepEqual(first.packet.record.moves,['575565']);
  assert.equal(last.packet.state,'finished');assert.equal(last.packet.record.moves.length,2);
  assert.equal(last.packet.record.moves[0],'575565');
  assert.deepEqual(last.packet.record.result,{Win:{winner:'White',reason:'Resignation'}});assert.equal(last.packet.record.termination,'Resignation');
}
const canonical=value=>Array.isArray(value)?'['+value.map(canonical).join(',')+']':value!==null&&typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);

async function main(){
  assert.equal(process.platform,'linux','Actual browser checks run on Linux, not a Mac.');
  const commit=process.env.GITHUB_SHA;assert.match(commit??'',/^[0-9a-f]{40}$/);
  const work=resolve(process.argv[2]);mkdirSync(work,{recursive:true});
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),web=join(root,'apps/web');
  const {chromium}=createRequire(join(web,'package.json'))('@playwright/test');
  const base='https://voxelshogi.yousan-apps.workers.dev';
  const report={schema:1,kind:'public-browser-storage',applicationCommit:commit,complete:false,syntheticOnly:true,gameIds:[],startedAt:new Date().toISOString()};
  const save=()=>writeFileSync(join(work,'public-storage.json'),JSON.stringify(report,null,2)+'\n');save();
  let browser;
  try{
    const published=await fetch(base+'/build-info.json',{cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
    assert.equal((await published.json()).commit,commit,'public application must match the recording source');
    browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}});page.setDefaultTimeout(20000);
    let errors=0;page.on('pageerror',()=>errors++);page.on('dialog',dialog=>dialog.accept());
    const isPost=response=>new URL(response.url()).origin===base&&new URL(response.url()).pathname==='/api/games'&&response.request().method()==='POST';
    page.on('request',request=>{
      if(new URL(request.url()).origin!==base||new URL(request.url()).pathname!=='/api/games'||request.method()!=='POST')return;
      const p=request.postDataJSON();
      if(typeof p?.gameId==='string'&&/^[0-9a-f-]{36}$/.test(p.gameId)&&!report.gameIds.includes(p.gameId)){report.gameIds.push(p.gameId);save();}
    });
    const metadata=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/collection');
    await page.goto(base,{waitUntil:'domcontentloaded'});await page.getByTestId('status').waitFor();
    const config=await(await metadata).json();assert.equal(config.enabled,true);assert.equal(config.policy,'automatic-game-v2');
    await page.getByRole('button',{name:'AIと対戦',exact:true}).click();
    await page.getByLabel('あなたの先後').selectOption('h-r');await page.getByLabel('相手のAI').selectOption('easy');
    await page.getByRole('button',{name:'対戦をはじめる',exact:true}).click();
    const firstResponse=page.waitForResponse(response=>isPost(response)&&response.request().postDataJSON()?.state==='progress');
    await page.locator('.board2d [data-square="382"]').click();await page.locator('.board2d [data-square="373"]').click();
    await page.waitForFunction(()=>document.querySelector('[data-testid="status"]')?.textContent==='3手目 ☗先手の番');
    const envelope=async response=>({httpStatus:response.status(),packet:response.request().postDataJSON(),ack:await response.json()});
    const first=await envelope(await firstResponse);report.first={httpStatus:first.httpStatus,ack:first.ack};save();
    const terminal=page.waitForResponse(response=>isPost(response)&&response.request().postDataJSON()?.state==='finished');
    await page.getByRole('button',{name:'対局設定',exact:true}).click();await page.getByRole('button',{name:'投了',exact:true}).click();
    const last=await envelope(await terminal);verifyBrowserStorageFlow(first,last,commit);
    const wasm=await import(pathToFileURL(join(web,'src/wasm/pkg/voxelshogi_wasm.js')));wasm.initSync({module:readFileSync(join(web,'src/wasm/pkg/voxelshogi_wasm_bg.wasm'))});
    const replay=wasm.Game.fromRecordJson(JSON.stringify(last.packet.record));try{assert.equal(replay.moveCount(),2);assert.equal(replay.isFinished(),true);}finally{replay.free();}
    await page.getByRole('button',{name:'閉じる',exact:true}).click();
    await page.screenshot({path:join(work,'public-storage.png'),fullPage:true});assert.equal(errors,0);
    const payload=canonical(last.packet),bytes=Buffer.from(payload);
    writeFileSync(join(work,'public-storage-payload.json'),payload+'\n');
    Object.assign(report,{complete:true,gameId:last.packet.gameId,version:last.packet.version,last:{httpStatus:last.httpStatus,ack:last.ack},
      payloadBytes:bytes.length,payloadSha256:createHash('sha256').update(bytes).digest('hex'),fullRecordReplayedByRust:true,d1ReadbackVerified:false});
  }finally{if(browser)await browser.close();report.finishedAt=new Date().toISOString();save();}
  console.log(JSON.stringify({complete:report.complete,gameIds:report.gameIds,applicationCommit:commit,d1ReadbackVerified:false}));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main();
