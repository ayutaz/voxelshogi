import assert from 'node:assert/strict';
import test from 'node:test';
import { verifyAudioVideo } from '../demo-bgm.mjs';

const source = { streams: [{ codec_type: 'video', codec_name: 'h264', width: 1080, height: 1350, avg_frame_rate: '30/1', nb_frames: '450' }], format: { duration: '15' } };
const output = { streams: [...source.streams, { codec_type: 'audio', codec_name: 'aac', sample_rate: '48000', channels: 2, duration: '15' }], format: { duration: '15' } };
test('BGM delivery requires actual stereo AAC and the identical source video', () => {
  assert.doesNotThrow(() => verifyAudioVideo(source, output, 'video-packets', 'video-packets', 15));
  assert.throws(() => verifyAudioVideo(source, source, 'same', 'same', 15));
  assert.throws(() => verifyAudioVideo(source, output, 'original', 'changed', 15));
  for (const change of [{ channels: 1 }, { sample_rate: '44100' }, { codec_name: 'mp3' }, { duration: '14' }]) {
    const bad = structuredClone(output); Object.assign(bad.streams[1], change);
    assert.throws(() => verifyAudioVideo(source, bad, 'same', 'same', 15));
  }
  const bad = structuredClone(output); bad.streams[0].nb_frames = '449';
  assert.throws(() => verifyAudioVideo(source, bad, 'same', 'same', 15));
});
