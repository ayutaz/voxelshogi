import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { browserMemory } from './browser-memory.mjs';
import { canonicalAction, fixedPositions, switchPrecisions, installPolicyBridge, runPolicyRequests } from './trained-benchmark.mjs';
import { trainedCases, validateTrainedEvidence, requireExternalLinux } from './trained-browser-evidence.mjs';
const root = fileURLToPath(new URL('../', import.meta.url));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const json = path => JSON.parse(readFileSync(path, 'utf8'));

async function positions(manifest) {
  const { initSync, Game } = await import(pathToFileURL(resolve(root,'apps/web/src/wasm/pkg/voxelshogi_wasm.js')));
  initSync({ module: readFileSync(resolve(root,'apps/web/src/wasm/pkg/voxelshogi_wasm_bg.wasm')) });
  return fixedPositions(manifest, text => Game.fromRecordJson(text), canonicalAction);
}
function observe() {
  const state = window.trainedObservation = { draws: 0, trustedCameraInputs: 0, gaps: [], last: null };
  const active = () => window.trainedBenchmark?.measuring && window.trainedBenchmark.pending;
  const tick = at => { if(active() && state.last!==null) state.gaps.push(at-state.last);state.last=active()?at:null;requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  window.addEventListener('pointermove',event=>{ if(event.target instanceof HTMLCanvasElement && event.isTrusted && event.buttons && active()) state.trustedCameraInputs++; },true);
  const draw=WebGL2RenderingContext.prototype.drawElementsInstanced;
  WebGL2RenderingContext.prototype.drawElementsInstanced=function(...args){ const value=draw.apply(this,args);if(active())state.draws++;return value; };
}
async function sampleMemory(cdp,page,work) {
  const samples=[], errors=[];let busy=null;
  const sample=()=>busy??=(async()=>{try{const value=await browserMemory(cdp,page);samples.push({...value,totalRssBytes:value.residentSet.totalRssBytes});}catch(error){errors.push(String(error));}})().finally(()=>{busy=null;});
  await sample();const timer=setInterval(()=>void sample(),1000);
  try { return { value:await work(), memory:{samples,maximumSamplingGapMs:0} }; }
  finally {
    clearInterval(timer);await busy;await sample();
    assert.deepEqual(errors,[],'resource sampling failed');
    const times=samples.map(s=>Date.parse(s.at));samples.maximumGap=times.length<2?Infinity:Math.max(...times.slice(1).map((t,i)=>t-times[i]));
    assert.ok(samples.maximumGap<=5000,'resource sampling gap exceeds five seconds');
  }
}
async function drag(page) {
  const box=await page.getByTestId('board3d').locator('canvas').boundingBox();assert.ok(box);
  await page.mouse.move(box.x+box.width*.4,box.y+box.height*.4);await page.mouse.down();
  await page.mouse.move(box.x+box.width*.6,box.y+box.height*.6,{steps:6});await page.mouse.up();
}

/** Linux only. A candidate catalog is local metadata interception, never a public proof. */
export async function measureTrainedModels({browser,base,modelFolder,catalog,output,candidate=false,smoke=false}) {
  requireExternalLinux(process.platform);
  const url=new URL(base);assert.ok(url.protocol==='https:' || (url.protocol==='http:' && ['127.0.0.1','localhost'].includes(url.hostname)),'secure or local application required');
  const manifestBytes=readFileSync(resolve(modelFolder,'manifest.json')),manifest=JSON.parse(manifestBytes);
  const release=catalog.releases.find(r=>r.id===manifest.id);assert.ok(release,'model not in verified catalog');
  assert.equal(sha(manifestBytes),release.manifest.sha256,'manifest differs from catalog');assert.equal(manifest.sourceCommit,release.sourceCommit);
  assert.equal(manifest.numericContract,'voxelshogi-trained-numeric-v1');assert.equal(manifest.trained,true);
  if(!smoke) assert.equal(manifest.ciFixture,undefined,'CI fixture is not a trained measurement');
  for(const variant of manifest.variants) { const bytes=readFileSync(resolve(modelFolder,variant.model.path));assert.equal(bytes.length,variant.model.bytes);assert.equal(sha(bytes),variant.model.sha256); }
  const cdp=await browser.newBrowserCDPSession(),gpu=await cdp.send('SystemInfo.getInfo'); // Initialize real GPU service before adapter requests.
  const fixtures=await positions(manifest);
  const report={schema:1,kind:'m6-trained-browser-measurement',platform:process.platform,mode:smoke?'smoke':'full',candidate,complete:false,base,startedAt:new Date().toISOString(),chrome:browser.version(),gpu:gpu.gpu,
    applicationCommit:null,renderer:null,model:{id:manifest.id,trained:true,numericContract:manifest.numericContract,packageHash:release.manifest.sha256,sourceCommit:manifest.sourceCommit,revision:release.revision,
      variants:manifest.variants.map(v=>({precision:v.id,sha256:v.model.sha256,bytes:v.model.bytes}))},fixtures,rows:[],switches:[],
    method:{warmup:10,measured:30,cold:'new browser context and Worker; OS/driver caches uncontrolled',reuse:'same validated Worker session for all repeated root requests',timing:'inference includes CPU output readback; round trip additionally includes Worker messaging',memory:'dedicated Chromium process RSS and main-page heap sampled once per second; observed values, not guaranteed peaks',rendering:'trusted camera input and real instanced draws observed during pending inference; no delayed replies',batch:1}};
  const save=()=>{mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');};save();
  let workerUrl=null, firstBuild=null;
  async function pageFor(show3D, position=fixtures[0]) {
    const context=await browser.newContext({viewport:{width:1440,height:1100}});
    if(candidate) await context.route('**/models/m6/catalog.json',route=>route.fulfill({json:catalog}));
    const page=await context.newPage(),lifecycle={created:0,closed:0,live:0};page.on('worker',worker=>{lifecycle.created++;lifecycle.live++;worker.on('close',()=>{lifecycle.closed++;lifecycle.live--;});});await page.addInitScript(observe);await page.goto(base+'/');
    try {
      const build=await (await context.request.get(base+'/inference-build.json')).json();
      if(firstBuild) assert.deepEqual(build,firstBuild,'application changed during measurement');else firstBuild=build;
      report.applicationCommit=build.commit;
      const worker=build.files.find(f=>/^assets\/policy\.worker-.*\.js$/.test(f.path));assert.ok(worker,'tested policy Worker missing');
      const bytes=await (await context.request.get(new URL(worker.path,base).href)).body();assert.equal(sha(bytes),worker.sha256);assert.equal(bytes.length,worker.bytes);workerUrl='/'+worker.path;
      if(!candidate) assert.deepEqual(await (await context.request.get(base+'/models/m6/catalog.json')).json(),catalog,'public catalog differs from measured release');
      await page.getByTestId('import').setInputFiles({name:'fixed-position.json',mimeType:'application/json',buffer:Buffer.from(position.root.recordJson)});
      await page.getByRole('alert').filter({hasText:'棋譜を読み込みました'}).waitFor();
      await page.getByRole('button',{name:show3D?'3D+2D':'2D',exact:true}).click();
      if(show3D) { await page.getByTestId('board3d').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('[data-testid="board3d"]')?.dataset.ready==='true');await page.getByTestId('board3d').scrollIntoViewIfNeeded(); }
      await page.evaluate(()=>{const input=document.createElement('input');input.type='file';input.multiple=true;input.setAttribute('webkitdirectory','');input.id='trained-benchmark-files';input.hidden=true;document.body.append(input);});
      await page.locator('#trained-benchmark-files').setInputFiles(modelFolder);
      await page.evaluate(()=>{window.__trainedFiles=[...document.querySelector('#trained-benchmark-files').files].map(file=>({path:file.webkitRelativePath,file}));});
      await page.evaluate(installPolicyBridge,{workerUrl});
      if(show3D) report.renderer=await page.evaluate(()=>{const gl=document.querySelector('[data-testid="board3d"] canvas').getContext('webgl2'),extension=gl.getExtension('WEBGL_debug_renderer_info');return gl.getParameter(extension?extension.UNMASKED_RENDERER_WEBGL:gl.RENDERER);});
      return {context,page,lifecycle};
    } catch(error) {await context.close();throw error;}
  }
  try {
    const cases=smoke?[{show3D:false,backend:'wasm',precision:'fp32',fixture:fixtures[0].name}]:trainedCases();
    for(const value of cases) {
      const row={...value,status:'running',selection:{modelId:manifest.id,packageHash:release.manifest.sha256,precision:value.precision,backend:value.backend}};report.rows.push(row);save();
      const {context,page,lifecycle}=await pageFor(value.show3D,fixtures.find(f=>f.name===value.fixture));
      try {
        await page.evaluate(selected=>window.trainedBenchmark.select(selected),row.selection);
        const fixed=fixtures.find(f=>f.name===value.fixture);
        const measured=await sampleMemory(cdp,page,async()=>{
          const coldPacket=await page.evaluate(runPolicyRequests,{root:fixed.root});if(coldPacket.error)throw Object.assign(new Error(coldPacket.error.message),{stage:coldPacket.error.stage});const cold=coldPacket.samples[0];
          let done=false;
          const repeating=page.evaluate(runPolicyRequests,{root:fixed.root,count:smoke?11:40,warmup:10});
          repeating.then(()=>{done=true;},()=>{done=true;});
          if(value.show3D) for(let attempt=0;attempt<20 && !done;attempt++) await drag(page);
          const packet=await repeating;if(packet.error)throw Object.assign(new Error(packet.error.message),{stage:packet.error.stage});const repeated=packet.samples;
          return {cold,repeated,interaction:await page.evaluate(()=>({draws:window.trainedObservation.draws,trustedCameraInputs:window.trainedObservation.trustedCameraInputs,maximumFrameGapMs:Math.max(0,...window.trainedObservation.gaps)}))};
        });
        const {cold,repeated,interaction}=measured.value;
        assert.ok(fixed.legal.some(m=>m.move===cold.choice.move && m.action===cold.choice.action),'actual Worker choice is not Rust-legal');
        for(const result of repeated) {assert.deepEqual(result.root,cold.root);assert.deepEqual(result.selection,row.selection);assert.ok(fixed.legal.some(m=>m.move===result.choice.move && m.action===result.choice.action));}
        Object.assign(row,{status:'done',cold:{inferenceMs:cold.inferenceMs,roundTripMs:cold.roundTripMs},warmupCount:10,samples:repeated.map(s=>({inferenceMs:s.inferenceMs,roundTripMs:s.roundTripMs})),choice:cold.choice,validation:cold.validation,interaction,memory:{samples:measured.memory.samples,maximumSamplingGapMs:measured.memory.samples.maximumGap}});
      } catch(error) {
        row.error={stage:error.stage ?? 'measurement',message:String(error.message ?? error)};
        row.status=value.backend==='webgpu' && row.error.stage==='initialization' && /shader-f16|outputs exceed .* tolerance|not supported|unsupported|WebGPU.*not available/i.test(row.error.message)?'unsupported':'failed';
      } finally {await context.close();row.workers={...lifecycle};assert.equal(lifecycle.live,0,'row Worker survived context close');row.afterWorkerClose=await browserMemory(cdp);save();console.log(JSON.stringify({stage:'trained-browser',...value,status:row.status,error:row.error}));}
    }
    for(const backend of smoke?['wasm']:['wasm','webgpu']) {
      const available=manifest.variants.map(v=>v.id).filter(p=>report.rows.filter(r=>r.backend===backend && r.precision===p).every(r=>r.status==='done'));
      if(smoke) available.splice(0,available.length,'fp32','fp16');
      const steps=smoke?['fp16','fp32']:switchPrecisions(available);
      const {context,page,lifecycle}=await pageFor(false),group={backend,initial:available[0],steps:[]};report.switches.push(group);
      try {
        const measured=await sampleMemory(cdp,page,async()=>{
          for(const precision of [group.initial,...steps]) {
            const selection={modelId:manifest.id,packageHash:release.manifest.sha256,precision,backend};
            await page.evaluate(s=>window.trainedBenchmark.select(s),selection);
            const packet=await page.evaluate(runPolicyRequests,{root:fixtures[0].root});if(packet.error)throw Object.assign(new Error(packet.error.message),{stage:packet.error.stage});const reply=packet.samples[0];
            if(group.baseline)group.steps.push({precision,packageHash:release.manifest.sha256,validation:reply.validation,inferenceMs:reply.inferenceMs,roundTripMs:reply.roundTripMs});
            else group.baseline={precision,validation:reply.validation};
            save();
          }
        });group.memory={samples:measured.memory.samples,maximumSamplingGapMs:measured.memory.samples.maximumGap};
      } finally{await context.close();group.workers={...lifecycle};assert.equal(lifecycle.live,0,'switch Worker survived context close');assert.equal(lifecycle.created,steps.length+1,'each format switch must create a new Worker');group.afterWorkerClose=await browserMemory(cdp);save();}
    }
    if(!smoke)report.summary=validateTrainedEvidence(report,{allowCandidate:candidate});
    else assert.ok(report.rows.every(r=>r.status==='done') && report.switches[0].steps.length===2,'smoke failed');
    report.complete=true;
  } catch(error){report.failure=String(error.stack ?? error);throw error;}
  finally{report.finishedAt=new Date().toISOString();save();await cdp.detach();}
  return report;
}
async function main() {
  requireExternalLinux(process.platform);
  const args=process.argv.slice(2),smoke=args.includes('--smoke'),candidate=args.includes('--candidate');
  const paths=args.filter(a=>!a.startsWith('--'));assert.equal(paths.length,4,'usage: MODEL_FOLDER CATALOG_JSON OUTPUT_JSON BASE_URL [--candidate] [--smoke]');
  assert.ok(args.every(a=>!a.startsWith('--') || ['--candidate','--smoke'].includes(a)));
  const require=createRequire(new URL('../apps/web/package.json',import.meta.url));
  const {chromium}=await import(pathToFileURL(resolve(dirname(require.resolve('@playwright/test')),'index.mjs')));
  const browser=await chromium.launch({headless:true,args:smoke?[]:['--enable-gpu','--use-angle=vulkan','--enable-features=Vulkan','--disable-vulkan-surface','--enable-unsafe-webgpu','--enable-precise-memory-info']});
  try{await measureTrainedModels({browser,modelFolder:resolve(paths[0]),catalog:json(paths[1]),output:resolve(paths[2]),base:paths[3].replace(/\/$/,''),candidate,smoke});}finally{await browser.close();}
}
if(import.meta.url===pathToFileURL(process.argv[1]).href)await main();
