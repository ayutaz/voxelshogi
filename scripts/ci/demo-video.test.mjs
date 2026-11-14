import assert from 'node:assert/strict';
import test from 'node:test';
import { contentStartFrame, selectHook, parseFrameRate, verifyVideo, zoomAtFrame, verifyRecordedBounds, foregroundBounds, storyCuts, storyFrameSource, verifyHumanModel } from '../demo-video.mjs';

test('model CTA requires an actual trained S reply with the pinned format and all four numeric checks',()=>{
  const release={repo:'voxelshogi/voxelshogi-transformer-s',revision:'a'.repeat(40),manifest:{sha256:'b'.repeat(64)}};
  const model={repo:release.repo,revision:release.revision,selection:{modelId:'voxelshogi-transformer-s-m6-314159-v1',packageHash:release.manifest.sha256,precision:'int8',backend:'wasm'}};
  const record={selectedAgents:{mode:'h-r',b:{controller:'human'},w:{controller:'ai',difficulty:'model',model}},record:{moves:['575565','535545']},observationsThroughCursor:[{reply:{kind:'model-result',model,result:{bestMove:'535545'},validation:{fixtures:Array.from({length:4},()=>({comparison:{policy:{exceeded:0},value:{exceeded:0}}}))}}}]};
  verifyHumanModel(record,release);
  for(const mutate of [r=>{r.observationsThroughCursor[0].reply.kind='result'},r=>{r.observationsThroughCursor[0].reply.model.selection.precision='fp32'},r=>{r.observationsThroughCursor[0].reply.validation.fixtures.pop()},r=>{r.observationsThroughCursor[0].reply.validation.fixtures[0].comparison.policy.exceeded=1},r=>{r.record.moves[1]='111222'}]){
    const bad=structuredClone(record);mutate(bad);assert.throws(()=>verifyHumanModel(bad,release));
  }
});

test('cuts out canvas resizing and keeps precisely 210/120/120 settled frames',()=>{
  const timeline={controlsStartFrame:240,ctaStartFrame:390};
  assert.deepEqual(storyCuts(timeline),[{start:0,end:210},{start:240,end:360},{start:390,end:510}]);
  for(const [output,source]of [[0,0],[209,209],[210,240],[329,359],[330,390],[449,509]])assert.equal(storyFrameSource(output,timeline),source);
  assert.throws(()=>storyFrameSource(450,timeline));
  assert.throws(()=>storyCuts({controlsStartFrame:200,ctaStartFrame:390}));
  assert.throws(()=>storyCuts({controlsStartFrame:240,ctaStartFrame:350}));
});

test('keeps the controls at native scale and limits the opening zoom',()=>{
  assert.equal(zoomAtFrame(0,1.1),1);assert.equal(zoomAtFrame(18,1.1),1.05);
  assert.equal(zoomAtFrame(24,1.1),1.1);assert.equal(zoomAtFrame(96,1.1),1.05);
  for(const frame of [102,209,210,225,329,330,449])assert.equal(zoomAtFrame(frame,1.1),1);
});
test('rejects UI cut at the right edge or entering either caption band',()=>{
  const rect={left:16,right:1064,top:180,bottom:1150};verifyRecordedBounds([rect]);
  for(const change of [{right:1081},{left:-1},{top:175},{bottom:1161}])assert.throws(()=>verifyRecordedBounds([{...rect,...change}]));
  // Real source-frame envelope measured before this fix: full board, not the caption pixels.
  verifyRecordedBounds([{left:249,right:868,top:355,bottom:1095}],1.12);
  assert.throws(()=>verifyRecordedBounds([{left:249,right:868,top:355,bottom:1095}],1.7));
  assert.throws(()=>verifyRecordedBounds([]));
});
test('measures actual foreground pixels and refuses an empty recording',()=>{
  const rgb=Buffer.from(Array.from({length:20},()=>[20,40,44]).flat());
  for(const index of [6,7,11,12])rgb.set([230,210,160],index*3);
  assert.deepEqual(foregroundBounds(rgb,5,4),{left:1,right:3,top:1,bottom:3});
  assert.throws(()=>foregroundBounds(Buffer.from(Array.from({length:20},()=>[20,40,44]).flat()),5,4));
});

const frame = color => Array(4).fill(color).flat();
test('starts at the first real frame after a sustained green recording marker', () => {
  const dark = frame([15, 17, 21]), green = frame([0, 254, 1]);
  assert.equal(contentStartFrame(Uint8Array.from([...dark, ...green, ...dark, ...green, ...green, ...green, ...dark, ...dark])), 6);
  assert.throws(() => contentStartFrame(Uint8Array.from([...dark, ...green, ...green])), /marker/);
  assert.throws(() => contentStartFrame(Uint8Array.from([...green, ...green, ...green])), /content/);
  assert.throws(() => contentStartFrame(new Uint8Array(13)), /frame/);
});
test('selects a real cross-layer board move with enough subsequent moves for the story', () => {
  const moves = ['575565', '535545', '575566', '111222', '999888', '222111'];
  assert.equal(selectHook(moves), 3);
  assert.throws(() => selectHook(['575565', 'P*566', '575566']), /cross-layer/);
});
test('prefers a central real cross-layer move that can be read in the close-up', () => {
  assert.equal(selectHook(['111222', '991891', '575566', '222111', '999888', '222111', '888999']), 3);
});
test('reads the actual recording frame rate and rejects missing or invalid timing', () => {
  assert.equal(parseFrameRate('25/1'), 25);
  assert.equal(parseFrameRate('30000/1001'), 30000 / 1001);
  for (const value of ['0/0', 'NaN', '25/0', '-1/1', '120/1']) assert.throws(() => parseFrameRate(value));
});
test('requires a playable fifteen-second H.264 export, not just a manifest', () => {
  const probe = { format: { duration: '15.000000' }, streams: [{ codec_type: 'video', codec_name: 'h264', width: 1080, height: 1350, pix_fmt: 'yuv420p', avg_frame_rate: '30/1', nb_frames: '450' }] };
  verifyVideo(probe, 15);
  for (const change of [{ width: 1920 }, { codec_name: 'vp9' }, { avg_frame_rate: '25/1' }, { nb_frames: '1' }]) assert.throws(() => verifyVideo({ ...probe, streams: [{ ...probe.streams[0], ...change }] }, 15));
  assert.throws(() => verifyVideo({ ...probe, format: { duration: '2.9' } }, 15));
});
