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
  const i = moves.findIndex((move, index) => index + 3 < moves.length && /^[1-9]{6}\+?$/.test(move) && move[2] !== move[5]);
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

const composition = `
html,body{margin:0!important;width:1080px!important;height:1350px!important;overflow:hidden!important;background:#0f1115!important}
.app{display:block!important;width:1080px!important;height:1350px!important}
.app>header,.panel,main>.intro,main>.playback,main>.row,main>.hands,main>.move-focus,main>.collection-panel{display:none!important}
main{display:block!important;padding:0!important;overflow:hidden!important;width:1080px!important;height:1350px!important}
.views{position:absolute!important;left:0!important;top:200px!important;width:1080px!important;height:950px!important;min-height:950px!important;display:block!important}
.board3d{width:1080px!important;height:950px!important;min-height:950px!important;border:0!important;border-radius:0!important}
`;
const controlsComposition = `
html,body{margin:0!important;width:1080px!important;height:1350px!important;overflow:hidden!important;background:#0f1115!important}
.app{padding-top:190px!important}
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

async function record(work, commit) {
  const require = createRequire(join(web, 'package.json'));
  const { chromium } = require('@playwright/test');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1,
    recordVideo: { dir: join(work, 'raw'), size: { width: 1080, height: 1350 } } });
  const errors = [];
  let video, conditions, hook;
  try {
    const page = await context.newPage(); video = page.video();
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.goto('http://127.0.0.1:4173/');
    await page.getByText('対局・AI設定', { exact: true }).click();
    await page.getByTestId('difficulty-b').selectOption('easy');
    await page.getByTestId('difficulty-w').selectOption('easy');
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
    await page.getByRole('button', { name: '立体で見る', exact: true }).click();
    await page.getByLabel('全層を同じ濃さで表示').check();
    await go(hook - 1);
    await page.getByText('対局・AI設定', { exact: true }).click();
    let style = await page.addStyleTag({ content: composition });
    await page.getByTestId('board3d').waitFor();
    await page.waitForFunction(() => document.querySelector('[data-testid="board3d"]')?.getAttribute('data-ready') === 'true');
    await orbit(0.05, -0.08); // Show the nine layers from the side using actual OrbitControls.
    await page.getByLabel('全層を同じ濃さで表示').evaluate(checkbox => checkbox.click());
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
    // Keep the established angle: an extra orbit would consume the short
    // controls shot. A single step branches from the selected history point.
    await page.getByTestId('ai-step').click();
    await page.waitForFunction(ply => document.querySelector('[data-testid="status"]')?.textContent?.startsWith(`${ply + 1}手目`), hook + 3, { polling: 50 });
    await at(8000); await page.getByTestId('toggle-run').click();
    await page.waitForFunction(ply => document.querySelector('[data-testid="status"]')?.textContent?.startsWith(`${ply + 1}手目`), hook + 4, { polling: 50 });
    await page.getByTestId('toggle-run').click();
    await at(9000); await page.getByTestId('ai-step').click();
    await page.waitForFunction(ply => document.querySelector('[data-testid="status"]')?.textContent?.startsWith(`${ply + 1}手目`), hook + 5, { polling: 50 });
    await at(11000); await controlsStyle.evaluate(node => node.remove()); style = await page.addStyleTag({ content: composition });
    await at(15400);
    conditions = await exportRecord('source-ai-record.json');
    assert.equal(conditions.applicationCommit, commit);
    assert.equal(conditions.record.moves[hook - 1][2] !== conditions.record.moves[hook - 1][5], true);
    assert.deepEqual(errors, [], 'browser runtime errors');
  } finally { await context.close(); await browser.close(); }
  assert.ok(video && conditions);
  return { raw: await video.path(), conditions, hook };
}

function render(raw, work, startFrame, sourceRate) {
  const font = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc';
  readFileSync(font); // Fail before creating a video with missing Japanese glyphs.
  const lines = {
    'hook-a.txt': '将棋、9層にした。', 'hook-b.txt': 'その一手、別の階へ。',
    'watch.txt': 'AI同士の対局を、眺める。', 'step.txt': '止めて、一手ずつ追える。',
    'cta.txt': 'ブラウザで観戦', 'url.txt': 'voxelshogi.yousan-apps.workers.dev',
    'alpha.txt': '研究用Alpha', 'agents.txt': 'Easy vs Easy・実対局の再生',
  };
  for (const [name, text] of Object.entries(lines)) writeFileSync(join(work, name), text + '\n');
  writeFileSync(join(work, 'captions.json'), JSON.stringify({ schema: 1, segments: [
    { start: 0, end: 3, text: lines['hook-a.txt'] }, { start: 3, end: 7, text: lines['watch.txt'] },
    { start: 7, end: 11, text: lines['step.txt'] }, { start: 11, end: 15, text: lines['cta.txt'], url: lines['url.txt'], note: lines['alpha.txt'] },
  ], agents: lines['agents.txt'], alternativeHook: lines['hook-b.txt'] }, null, 2) + '\n');
  const text = (file, y, size, enable) => `drawtext=fontfile=${font}:textfile=${file}:x=(w-text_w)/2:y=${y}:fontsize=${size}:fontcolor=white:borderw=3:bordercolor=0x0f1115${enable ? `:enable='${enable}'` : ''}`;
  const timeline = `trim=start_frame=${startFrame},setpts=PTS-STARTPTS,fps=30`;
  const draw = ["drawbox=x=0:y=1240:w=iw:h=110:color=0x0f1115:t=fill:enable='gte(t,7)*lt(t,11)'", text('hook-a.txt', 76, 78, 'lt(t,3)'), text('watch.txt', 76, 60, 'gte(t,3)*lt(t,7)'),
    text('step.txt', 76, 60, 'gte(t,7)*lt(t,11)'), text('cta.txt', 76, 78, 'gte(t,11)'),
    text('url.txt', 1190, 43, 'gte(t,11)'), text('alpha.txt', 1260, 30, 'gte(t,11)'),
    text('agents.txt', 1280, 30, 'lt(t,11)')];
  const encode = (name, seconds, filters) => {
    run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', raw, '-vf', [timeline, ...filters].join(','),
      '-frames:v', String(seconds * 30), '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '22', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', name], { cwd: work });
    verifyVideo(probe(join(work, name)), seconds);
  };
  assert.ok(sourceRate >= 10);
  encode('demo-main.mp4', 15, draw);
  encode('hook-a.mp4', 3, [text('hook-a.txt', 76, 78), text('agents.txt', 1280, 30)]);
  encode('hook-b.mp4', 3, ["zoompan=z='1.12-0.12*min(on/89,1)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1350:fps=30", text('hook-b.txt', 76, 72), text('agents.txt', 1280, 30)]);
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
    const captured = await record(work, commit);
    const wasm = await import(pathToFileURL(join(web, 'src/wasm/pkg/voxelshogi_wasm.js')));
    wasm.initSync({ module: readFileSync(join(web, 'src/wasm/pkg/voxelshogi_wasm_bg.wasm')) });
    const replay = wasm.Game.fromRecordJson(JSON.stringify(captured.conditions.record));
    try { assert.ok(replay.moveCount() >= captured.hook + 5); } finally { replay.free(); }
    const rawProbe = probe(captured.raw), stream = rawProbe.streams.find(stream => stream.codec_type === 'video');
    const sourceRate = parseFrameRate(stream.avg_frame_rate);
    const pixels = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-i', captured.raw, '-vf', 'crop=2:2:0:0', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], { maxBuffer: 1024 * 1024 });
    assert.equal(pixels.status, 0, String(pixels.stderr));
    const startFrame = contentStartFrame(pixels.stdout);
    assert.ok(Number(rawProbe.format.duration) - startFrame / sourceRate >= 15, 'not enough real footage');
    render(captured.raw, work, startFrame, sourceRate);
    const outputs = ['demo-main.mp4', 'hook-a.mp4', 'hook-b.mp4', 'poster.png', 'ogp.png', 'contact-sheet.png', 'source-ai-record.json', 'captions.json'];
    const receipt = { schema: 1, kind: 'voxelshogi-demo-video', appCommit: commit, ruleset: 'voxelshogi-standard-v1',
      candidate: process.env.GITHUB_EVENT_NAME !== 'workflow_dispatch' || process.env.GITHUB_REF !== 'refs/heads/main',
      agents: ['easy', 'easy'], hookPly: captured.hook, hookMove: captured.conditions.record.moves[captured.hook - 1],
      fullRecordReplayedByRust: true, sourceRate, firstContentFrame: startFrame, outputFps: 30,
      performanceMeasurement: false, soundRequired: false,
      recordingScriptSha256: sha(fileURLToPath(import.meta.url)), webLockSha256: sha(join(web, 'pnpm-lock.yaml')),
      ffmpeg: run('ffmpeg', ['-version']).split('\n')[0], japaneseFontSha256: sha('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'),
      files: outputs.map(name => ({ path: name, bytes: readFileSync(join(work, name)).length, sha256: sha(join(work, name)) })) };
    writeFileSync(join(work, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
    console.log(JSON.stringify({ output: work, appCommit: commit, hookMove: receipt.hookMove, files: outputs }));
  } finally { if (server.pid && server.exitCode === null) { try { process.kill(-server.pid, 'SIGTERM'); } catch { /* exited */ } } }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) await main();
