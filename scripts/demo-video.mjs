import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

export function contentStartFrame(rgb) {
  assert.ok(rgb.length > 0 && rgb.length % 12 === 0, 'invalid marker sample frame data');
  let green = 0;
  for (let frame = 0; frame < rgb.length / 12; frame++) {
    let marker = true;
    for (let pixel = 0; pixel < 4; pixel++) {
      const offset = frame * 12 + pixel * 3;
      marker &&= rgb[offset] < 40 && rgb[offset + 1] > 220 && rgb[offset + 2] < 40;
    }
    if (marker) green++;
    else if (green >= 3) return frame;
    else green = 0;
  }
  assert.ok(green < 3, 'recording marker has no following content');
  throw new Error('recording marker not found');
}
export function selectHook(moves) {
  const centrality = move => [0, 1, 3, 4].reduce((n, p) => n + Math.abs(Number(move[p]) - 5), 0) + 2 * (Math.abs(Number(move[2]) - 5) + Math.abs(Number(move[5]) - 5));
  const candidates = moves.map((move, index) => ({ move, index })).filter(({move,index}) => index + 3 < moves.length && /^[1-9]{6}\+?$/.test(move) && move[2] !== move[5]);
  candidates.sort((a,b) => centrality(a.move) - centrality(b.move) || a.index - b.index);
  const i = candidates[0]?.index ?? -1;
  assert.ok(i >= 0, 'no real cross-layer move with enough following plies');
  return i + 1;
}
export function parseFrameRate(text) {
  assert.match(text, /^\d+\/\d+$/, 'invalid frame rate');
  const [a, b] = text.split('/').map(Number), rate = a / b;
  assert.ok(Number.isFinite(rate) && rate >= 10 && rate <= 60, 'unsupported frame rate');
  return rate;
}
export function verifyVideo(probe, seconds) {
  const stream = probe.streams.find(stream => stream.codec_type === 'video');
  assert.ok(stream, 'video stream missing');
  assert.equal(stream.codec_name, 'h264'); assert.equal(stream.width, 1080); assert.equal(stream.height, 1350);
  assert.equal(stream.pix_fmt, 'yuv420p'); assert.equal(parseFrameRate(stream.avg_frame_rate), 30);
  assert.equal(Number(stream.nb_frames), seconds * 30);
  assert.ok(Math.abs(Number(probe.format.duration) - seconds) <= 1 / 30, 'incorrect video duration');
}

export function verifyHumanModel(record, release) {
  assert.equal(record.selectedAgents.mode, 'h-r'); assert.equal(record.selectedAgents.b.controller, 'human');
  assert.equal(record.selectedAgents.w.difficulty, 'model'); assert.equal(record.record.moves.length, 2);
  assert.equal(record.observationsThroughCursor.length, 1);
  const reply=record.observationsThroughCursor[0].reply;
  assert.equal(reply.kind, 'model-result'); assert.equal(reply.result.bestMove, record.record.moves[1]);
  assert.equal(reply.model.repo, release.repo); assert.equal(reply.model.revision, release.revision);
  assert.deepEqual(reply.model.selection, {modelId:'voxelshogi-transformer-s-m6-314159-v1',packageHash:release.manifest.sha256,precision:'int8',backend:'wasm'});
  assert.equal(reply.validation.fixtures.length, 4);
  assert.ok(reply.validation.fixtures.every(f=>f.comparison.policy.exceeded===0&&f.comparison.value.exceeded===0));
}

export function zoomAtFrame(frame, maximum) {
  if(frame<12)return 1;
  if(frame<24)return 1+(frame-12)*(maximum-1)/12;
  if(frame<90)return maximum;
  if(frame<102)return maximum-(frame-90)*(maximum-1)/12;
  return 1; // UI controls are never cropped or enlarged.
}
export function verifyRecordedBounds(rects, zoom=1) {
  assert.ok(rects.length>0,'recorded content is missing');
  for(const rect of rects){
    const r={left:540+(rect.left-540)*zoom,right:540+(rect.right-540)*zoom,
      top:675+(rect.top-675)*zoom,bottom:675+(rect.bottom-675)*zoom};
    assert.ok(Object.values(r).every(Number.isFinite)&&r.right>r.left&&r.bottom>r.top,'invalid content bounds');
    assert.ok(r.left>=0&&r.right<=1080&&r.top>=176&&r.bottom<=1160,`content intersects a caption band or frame edge: ${JSON.stringify(r)}`);
  }
}
export function foregroundBounds(rgb,width,height) {
  assert.equal(rgb.length,width*height*3);
  let left=width,right=0,top=height,bottom=0;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=(y*width+x)*3;
    if(Math.max(Math.abs(rgb[i]-20),Math.abs(rgb[i+1]-40),Math.abs(rgb[i+2]-44))<=40)continue;
    left=Math.min(left,x);right=Math.max(right,x+1);top=Math.min(top,y);bottom=Math.max(bottom,y+1);
  }
  assert.ok(right>left&&bottom>top,'no visible board foreground');
  return {left,right,top,bottom};
}
export function storyCuts(timeline) {
  assert.ok(Number.isSafeInteger(timeline.controlsStartFrame)&&timeline.controlsStartFrame>=210);
  assert.ok(Number.isSafeInteger(timeline.ctaStartFrame)&&timeline.ctaStartFrame>=timeline.controlsStartFrame+120);
  return [{start:0,end:210},{start:timeline.controlsStartFrame,end:timeline.controlsStartFrame+120},
    {start:timeline.ctaStartFrame,end:timeline.ctaStartFrame+120}];
}
export function storyFrameSource(frame,timeline) {
  assert.ok(Number.isSafeInteger(frame)&&frame>=0&&frame<450);
  let offset=0;
  for(const cut of storyCuts(timeline)){
    if(frame<offset+cut.end-cut.start)return cut.start+frame-offset;
    offset+=cut.end-cut.start;
  }
}

const composition = `
html,body{margin:0!important;width:1080px!important;height:1350px!important;overflow:hidden!important;background:#14282c!important}
.arena-app{display:block!important;width:1080px!important;height:1350px!important;padding:0!important}
.arena-app>.masthead,.arena-app>.entry-tabs,.arena-app>.intro,.match-detail,.arena-board>:not(.views){display:none!important}
.arena-main,.arena-board{display:block!important;padding:0!important;overflow:hidden!important;width:1080px!important;height:1350px!important}
.views{position:absolute!important;left:0!important;top:200px!important;width:1080px!important;height:950px!important;min-height:950px!important;display:block!important}
.board3d{width:1080px!important;height:950px!important;min-height:950px!important;border:0!important;border-radius:0!important}
`;
const controlsComposition = `
html,body{margin:0!important;width:1080px!important;height:1350px!important;overflow:hidden!important;background:#0f1115!important}
.arena-app{padding-top:180px!important;padding-bottom:200px!important}
.arena-board{grid-template-rows:44px 42px minmax(170px,1fr) 52px 150px!important}
.playback button{font-size:18px!important;height:52px!important}.playback>.row{height:52px!important}
.playback-options>label{font-size:14px!important}.layer-rail button{font-size:16px!important}
`;
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const web = join(root, 'apps/web');
const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, ...options });
  assert.equal(result.status, 0, `${command} failed: ${String(result.stderr).slice(-4000)}`);
  return result.stdout;
};
const probe = file => JSON.parse(run('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', file]));
const sha = file => createHash('sha256').update(readFileSync(file)).digest('hex');

async function record(work, commit, site) {
  const require = createRequire(join(web, 'package.json'));
  const { chromium } = require('@playwright/test');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1,
    recordVideo: { dir: join(work, 'raw'), size: { width: 1080, height: 1350 } } });
  // Synthetic recording games never enter production D1; model and UI requests stay real.
  await context.route('**/api/collection',route=>route.fulfill({json:{enabled:true,policy:'automatic-game-v2',schemas:[1,2]}}));
  await context.route('**/api/games',route=>{const p=route.request().postDataJSON();return route.fulfill({json:{gameId:p.gameId,requestId:p.requestId,version:p.version,status:'received_unverified'}})});
  const errors = [];
  let video, conditions, humanConditions, hook, timeline;
  const uiLayouts=[];
  try {
    const page = await context.newPage(); video = page.video();
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.goto(site);
    await page.getByRole('button', { name: '対局設定', exact: true }).click();
    await page.getByTestId('difficulty-b').selectOption('easy');
    await page.getByTestId('difficulty-w').selectOption('easy');
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    const exportRecord = async name => {
      const download = page.waitForEvent('download');
      // Disclosure panels may be hidden by the composition-only recording CSS.
      await page.getByTestId('export-ai-record').evaluate(button => button.click());
      await (await download).saveAs(join(work, name));
      return JSON.parse(readFileSync(join(work, name), 'utf8'));
    };
    // Actual Easy Workers choose every move; there is no fabricated AI or new training.
    for (let i = 0; i < 32; i++) {
      await page.getByTestId('ai-step').click();
      await page.waitForFunction(ply => document.querySelector('[data-testid="status"]')?.textContent?.startsWith(`${ply + 1}手目`), i + 1);
      await page.waitForFunction(() => document.querySelector('[data-testid="ai-phase"]')?.textContent === '一時停止中');
    }
    conditions = await exportRecord('initial-ai-record.json');
    assert.equal(conditions.applicationCommit, commit);
    assert.equal(conditions.selectedAgents.b.difficulty, 'easy');
    assert.equal(conditions.selectedAgents.w.difficulty, 'easy');
    hook = selectHook(conditions.record.moves);
    const go = async ply => {
      await page.getByTestId('move-list').locator('button').nth(ply).evaluate(button => button.click());
      await page.waitForFunction(expected => document.querySelector('[data-testid="status"]')?.textContent?.startsWith(`${expected + 1}手目`), ply, { polling: 50 });
    };
    const orbit = async (horizontal, vertical) => {
      const box = await page.getByTestId('board3d').locator('canvas').boundingBox();
      assert.ok(box && box.height > 0, 'real canvas bounds required');
      const x = box.x + box.width / 2, y = box.y + box.height / 2;
      await page.mouse.move(x, y); await page.mouse.down();
      await page.mouse.move(x + box.height * horizontal, y + box.height * vertical, { steps: 10 });
      await page.mouse.up();
    };
    await page.getByRole('button', { name: '立体で眺める', exact: true }).click();
    await page.getByRole('button', { name: '表示設定', exact: true }).click();
    await page.getByLabel('全層を同じ濃さで表示').check();
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    await go(hook - 1);
    let style = await page.addStyleTag({ content: composition });
    await page.getByTestId('board3d').waitFor();
    await page.waitForFunction(() => document.querySelector('[data-testid="board3d"]')?.getAttribute('data-ready') === 'true');
    await orbit(0.05, -0.04); // Show the nine layers from the side using actual OrbitControls.
    await delay(1000);
    await page.evaluate(() => {
      const marker = document.createElement('div'); marker.id = 'recording-marker';
      marker.style.cssText = 'position:fixed;inset:0;background:#00ff00;z-index:2147483647'; document.body.append(marker);
    });
    await delay(1000);
    await page.evaluate(() => document.getElementById('recording-marker').remove());
    const began = performance.now();
    const at = async milliseconds => { assert.ok(performance.now() - began < milliseconds + 1500, 'recording missed its story timing'); await delay(Math.max(0, milliseconds - (performance.now() - began))); };
    await at(700); await go(hook);
    assert.ok(performance.now() - began < 2200, 'hook move arrived too late for the first three seconds');
    await at(3000);
    await go(hook + 1);
    await at(5000); await go(hook + 2);
    await at(7000); await style.evaluate(node => node.remove());
    const controlsStyle = await page.addStyleTag({ content: controlsComposition });
    const settledCanvas=async()=>{
      await page.waitForFunction(()=>{
        const canvas=document.querySelector('[data-testid="board3d"] canvas');if(!canvas)return false;
        const r=canvas.getBoundingClientRect();return Math.abs(canvas.width-r.width)<2&&Math.abs(canvas.height-r.height)<2;
      });
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      await delay(300); // ResizeObserver/R3F update frames are deliberately excluded from the edit.
    };
    await settledCanvas();
    const checkControls=async()=>{
      const rects=await page.locator('.masthead,.entry-tabs,.board2d-grid,.playback button,.playback input,.layer-rail button,.follow-explanation').evaluateAll(nodes=>nodes.map(node=>{
        const r=node.getBoundingClientRect();return{left:r.left,right:r.right,top:r.top,bottom:r.bottom};
      }).filter(r=>r.right>r.left&&r.bottom>r.top));
      verifyRecordedBounds(rects);uiLayouts.push({atMilliseconds:performance.now()-began,rects});
    };
    await checkControls();
    timeline={controlsStartFrame:Math.ceil((performance.now()-began)*30/1000)};
    // Keep the established angle: an extra orbit would consume the short
    // controls shot. A single step branches from the selected history point.
    await delay(500);await page.getByTestId('ai-step').click();
    await page.waitForFunction(ply => document.querySelector('[data-testid="status"]')?.textContent?.startsWith(`${ply + 1}手目`), hook + 3, { polling: 50 });
    assert.equal(await page.getByTestId('ai-phase').textContent(), '一時停止中');
    await checkControls();await at((timeline.controlsStartFrame/30+3.8)*1000);await checkControls();
    await at((timeline.controlsStartFrame/30+4.2)*1000);
    conditions = await exportRecord('source-ai-record.json');
    assert.equal(conditions.applicationCommit, commit);
    assert.equal(conditions.record.moves[hook - 1][2] !== conditions.record.moves[hook - 1][5], true);
    // Record a separate real human/S game. Preparation/resize frames stay outside the edit.
    await page.getByRole('button',{name:'AIと対戦',exact:true}).click();
    await page.getByLabel('あなたの先後').selectOption('h-r');
    await page.getByLabel('相手のAI').selectOption('model');
    await page.getByLabel('モデルの精度形式').waitFor({timeout:60000});
    await page.getByLabel('モデルの精度形式').selectOption('int8');
    await page.getByRole('button',{name:'対戦をはじめる',exact:true}).click();
    await page.getByRole('button',{name:/^V層を見る(?:、|$)/}).click();
    await page.locator('.board2d [data-square="382"]').click();
    await page.locator('.board2d [data-square="373"]').click();
    await page.waitForFunction(()=>document.querySelector('[data-testid="status"]')?.textContent?.startsWith('3手目'),{},{timeout:120000});
    humanConditions=await exportRecord('source-human-record.json');
    assert.equal(humanConditions.applicationCommit,commit);
    const release=JSON.parse(readFileSync(join(web,'public/models/m6/catalog.json'))).releases.find(r=>r.publicDownload===true);
    assert.ok(release);verifyHumanModel(humanConditions,release);
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));await delay(300);
    await checkControls();timeline.ctaStartFrame=Math.ceil((performance.now()-began)*30/1000);
    await at((timeline.ctaStartFrame/30+4.4)*1000);await checkControls();
    assert.deepEqual(errors, [], 'browser runtime errors');
  } finally { await context.close(); await browser.close(); }
  assert.ok(video && conditions);
  assert.ok(timeline);storyCuts(timeline);
  return { raw: await video.path(), conditions, humanConditions, hook, uiLayouts, timeline };
}

function render(raw, work, startFrame, sourceRate, hookMove, timing) {
  const font = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc';
  readFileSync(font); // Fail before creating a video with missing Japanese glyphs.
  const lines = {
    'hook-a.txt': '将棋、9層にした。', 'hook-b.txt': 'その一手、別の階へ。',
    'watch.txt': 'AI同士の対局を、眺める。', 'step.txt': '止めて、一手ずつ追える。',
    'cta.txt': '開発したAIと、あなたが対戦。', 'url.txt': 'voxelshogi.yousan-apps.workers.dev',
    'alpha.txt': '学習済みS・INT8（重み）／申請・ログイン不要', 'agents.txt': 'Easy vs Easy・実対局の再生',
    'cross.txt': `${['I','II','III','IV','V','VI','VII','VIII','IX'][Number(hookMove[2])-1]}層 → ${['I','II','III','IV','V','VI','VII','VIII','IX'][Number(hookMove[5])-1]}層`,
  };
  for (const [name, text] of Object.entries(lines)) writeFileSync(join(work, name), text + '\n');
  writeFileSync(join(work, 'captions.json'), JSON.stringify({ schema: 1, segments: [
    { start: 0, end: 3, text: lines['hook-a.txt'] }, { start: 3, end: 7, text: lines['watch.txt'] },
    { start: 7, end: 11, text: lines['step.txt'] }, { start: 11, end: 15, text: lines['cta.txt'], url: lines['url.txt'], note: lines['alpha.txt'] },
  ], agents: lines['agents.txt'], crossLayer: lines['cross.txt'], alternativeHook: lines['hook-b.txt'] }, null, 2) + '\n');
  const text = (file, y, size, enable) => `drawtext=fontfile=${font}:textfile=${file}:x=(w-text_w)/2:y=${y}:fontsize=${size}:fontcolor=white:borderw=3:bordercolor=0x0f1115${enable ? `:enable='${enable}'` : ''}`;
  const timeline = `trim=start_frame=${startFrame},setpts=PTS-STARTPTS,fps=30`;
  const cuts=storyCuts(timing);
  const settledStory=`[0:v]${timeline},split=3[s0][s1][s2];`+cuts.map((cut,i)=>`[s${i}]trim=start_frame=${cut.start}:end_frame=${cut.end},setpts=PTS-STARTPTS[c${i}];`).join('')+'[c0][c1][c2]concat=n=3:v=1:a=0[story];';
  // Full nine-layer view at frame 0, then enlarge the actual central cross-layer move.
  // Caption compositing follows the crop, so the opening words stay readable.
  const zoom = maximum => `zoompan=z='if(lt(on,12),1,if(lt(on,24),1+(on-12)*${maximum-1}/12,if(lt(on,90),${maximum},if(lt(on,102),${maximum}-(on-90)*${maximum-1}/12,1))))':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1350:fps=30`;
  const bands=['drawbox=x=0:y=0:w=iw:h=176:color=0x10191c:t=fill','drawbox=x=0:y=1160:w=iw:h=190:color=0x10191c:t=fill'];
  const draw = [zoom(1.1), ...bands, text('hook-a.txt', 76, 78, 'lt(t,3)'), text('watch.txt', 76, 60, 'gte(t,3)*lt(t,7)'),
    text('step.txt', 76, 60, 'gte(t,7)*lt(t,11)'), text('cta.txt', 76, 54, 'gte(t,11)'),
    text('url.txt', 1190, 43, 'gte(t,11)'), text('alpha.txt', 1260, 30, 'gte(t,11)'),
    text('agents.txt', 1280, 30, 'lt(t,11)'), text('cross.txt', 1180, 46, 'gte(t,0.7)*lt(t,3)')];
  const encode = (name, seconds, filters) => {
    run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', raw, '-filter_complex', settledStory+'[story]'+filters.join(',')+'[out]', '-map','[out]',
      '-frames:v', String(seconds * 30), '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '22', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', name], { cwd: work });
    verifyVideo(probe(join(work, name)), seconds);
    run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-xerror', '-i', name, '-map', '0:v:0', '-f', 'null', '-'], { cwd: work });
  };
  assert.ok(sourceRate >= 10);
  encode('demo-main.mp4', 15, draw);
  encode('hook-a.mp4', 3, [zoom(1.1), ...bands, text('hook-a.txt', 76, 78), text('agents.txt', 1280, 30), text('cross.txt', 1180, 46, 'gte(t,0.7)')]);
  encode('hook-b.mp4', 3, [zoom(1.12), ...bands, text('hook-b.txt', 76, 72), text('agents.txt', 1280, 30), text('cross.txt', 1180, 46, 'gte(t,0.7)')]);
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', 'demo-main.mp4', '-frames:v', '1', 'poster.png'], { cwd: work });
  // A real board frame on the right, with sharing copy outside the board.
  const ogpText = (file, y, size) => `drawtext=fontfile=${font}:textfile=${file}:x=40:y=${y}:fontsize=${size}:fontcolor=white`;
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', 'demo-main.mp4', '-vf',
    ['crop=1080:950:0:200', 'scale=650:572', 'pad=1200:630:550:29:color=0x0f1115', ogpText('hook-a.txt', 190, 46), ogpText('watch.txt', 290, 30), ogpText('alpha.txt', 390, 26)].join(','), '-frames:v', '1', 'ogp.png'], { cwd: work });
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', 'demo-main.mp4', '-vf', "select='eq(n,0)+eq(n,21)+eq(n,45)+eq(n,87)+eq(n,225)+eq(n,345)',scale=360:450,tile=3x2", '-frames:v', '1', 'contact-sheet.png'], { cwd: work });
}

async function main() {
  assert.equal(process.platform, 'linux', 'Continuous capture and encoding run on Linux CI, not a Mac.');
  const commit = process.env.GITHUB_SHA ?? run('git', ['rev-parse', 'HEAD'], { cwd: root }).trim();
  assert.match(commit, /^[0-9a-f]{40}$/);
  const candidate = process.env.GITHUB_EVENT_NAME !== 'workflow_dispatch' || process.env.GITHUB_REF !== 'refs/heads/main';
  if (!candidate) {
    const published = await fetch('https://voxelshogi.yousan-apps.workers.dev/build-info.json', { cache: 'no-store', signal: AbortSignal.timeout(15000) });
    assert.ok(published.ok, 'public build metadata unavailable');
    assert.equal((await published.json()).commit, commit, 'record the current public application commit');
  }
  const work = resolve(process.argv[2] ?? join(root, 'runs/demo-video')); mkdirSync(work, { recursive: true });
  const server = spawn('pnpm', ['--dir', web, 'exec', 'vite', 'preview', '--host', '127.0.0.1', '--port', '4173', '--strictPort'], { detached: true, stdio: 'ignore' });
  let spawnError; server.on('error', error => { spawnError = error; });
  try {
    let ready = false;
    for (let attempt = 0; attempt < 40; attempt++) {
      if (spawnError) throw spawnError;
      try { const response = await fetch('http://127.0.0.1:4173/build-info.json', { signal: AbortSignal.timeout(1000) }); if ((await response.json()).commit === commit) { ready = true; break; } } catch { /* finite local server startup */ }
      await delay(250);
    }
    assert.ok(ready, 'tested app commit did not start');
    const captured = await record(work, commit, candidate ? 'http://127.0.0.1:4173/' : 'https://voxelshogi.yousan-apps.workers.dev/');
    const wasm = await import(pathToFileURL(join(web, 'src/wasm/pkg/voxelshogi_wasm.js')));
    wasm.initSync({ module: readFileSync(join(web, 'src/wasm/pkg/voxelshogi_wasm_bg.wasm')) });
    const replay = wasm.Game.fromRecordJson(JSON.stringify(captured.conditions.record));
    try { assert.equal(replay.moveCount(), captured.hook + 3); } finally { replay.free(); }
    const humanReplay=wasm.Game.fromRecordJson(JSON.stringify(captured.humanConditions.record));
    try { assert.equal(humanReplay.moveCount(),2); } finally { humanReplay.free(); }
    const rawProbe = probe(captured.raw), stream = rawProbe.streams.find(stream => stream.codec_type === 'video');
    const sourceRate = parseFrameRate(stream.avg_frame_rate);
    const pixels = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-i', captured.raw, '-vf', 'crop=2:2:0:0', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], { maxBuffer: 1024 * 1024 });
    assert.equal(pixels.status, 0, String(pixels.stderr));
    const startFrame = contentStartFrame(pixels.stdout);
    assert.ok(Number(rawProbe.format.duration) - startFrame / sourceRate >= storyCuts(captured.timeline).at(-1).end/30, 'not enough settled footage');
    const boardBounds=[];
    for(const seconds of [0,0.4,0.7,1.5,2.9,3.2,6.9]){
      const frame=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-ss',String(startFrame/sourceRate+storyFrameSource(Math.round(seconds*30),captured.timeline)/30),'-i',captured.raw,
        '-vf','crop=1080:950:0:200','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'],{maxBuffer:4*1024*1024});
      assert.equal(frame.status,0,String(frame.stderr));const r=foregroundBounds(frame.stdout,1080,950),rect={...r,top:r.top+200,bottom:r.bottom+200};
      const zoom=zoomAtFrame(Math.round(seconds*30),seconds<3?1.12:1.1);
      verifyRecordedBounds([rect],zoom);boardBounds.push({seconds,rect,zoom});
    }
    render(captured.raw, work, startFrame, sourceRate, captured.conditions.record.moves[captured.hook-1],captured.timeline);
    const reviewFrames=[];
    for(const [name,times]of [['main',[0,0.4,0.7,1.5,2.9,3,3.2,6.9,7,7.2,7.5,10.8,11,11.2,14.9]],['a',[0,1.5,2.9]],['b',[0,1.5,2.9]]]){
      for(const seconds of times){
        const file=`review-${name}-${String(seconds).replace('.','-')}.png`;
        run('ffmpeg',['-hide_banner','-loglevel','error','-y','-ss',String(seconds),'-i',name==='main'?'demo-main.mp4':`hook-${name}.mp4`,'-frames:v','1',file],{cwd:work});
        reviewFrames.push({file,seconds,source:name});
      }
    }
    writeFileSync(join(work,'framing.json'),JSON.stringify({schema:1,captionBands:{top:[0,176],bottom:[1160,1350]},
      openingZoom:{a:1.1,b:1.12},controlsZoom:1,timeline:captured.timeline,sourceCuts:storyCuts(captured.timeline),uiLayouts:captured.uiLayouts,boardBounds,reviewFrames,
      recordedBoundsVerified:true,visualReviewComplete:false},null,2)+'\n');
    const outputs = ['demo-main.mp4', 'hook-a.mp4', 'hook-b.mp4', 'poster.png', 'ogp.png', 'contact-sheet.png', 'source-ai-record.json', 'source-human-record.json', 'captions.json','framing.json',...reviewFrames.map(f=>f.file)];
    const receipt = { schema: 1, kind: 'voxelshogi-demo-video', appCommit: commit, ruleset: 'voxelshogi-standard-v1',
      candidate,
      captureOrigin: candidate ? 'http://127.0.0.1:4173' : 'https://voxelshogi.yousan-apps.workers.dev',
      agents: ['easy', 'easy'], hookPly: captured.hook, hookMove: captured.conditions.record.moves[captured.hook - 1],
      humanModel:captured.humanConditions.selectedAgents.w.model, humanModelReplyVerified:true,
      fullRecordReplayedByRust: true, fullDecodeValidated: true, recordedBoundsVerified:true, sourceRate, firstContentFrame: startFrame, outputFps: 30,
      performanceMeasurement: false, soundRequired: false,
      recordingScriptSha256: sha(fileURLToPath(import.meta.url)), webLockSha256: sha(join(web, 'pnpm-lock.yaml')),
      ffmpeg: run('ffmpeg', ['-version']).split('\n')[0], japaneseFontSha256: sha('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'),
      files: outputs.map(name => ({ path: name, bytes: readFileSync(join(work, name)).length, sha256: sha(join(work, name)) })) };
    writeFileSync(join(work, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
    console.log(JSON.stringify({ output: work, appCommit: commit, hookMove: receipt.hookMove, files: outputs }));
  } finally { if (server.pid && server.exitCode === null) { try { process.kill(-server.pid, 'SIGTERM'); } catch { /* exited */ } } }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) await main();
