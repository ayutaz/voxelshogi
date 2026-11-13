import assert from 'node:assert/strict';
import test from 'node:test';
import { contentStartFrame, selectHook, parseFrameRate, verifyVideo } from '../demo-video.mjs';

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
