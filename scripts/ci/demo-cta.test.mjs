import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyCtaSource, verifyCtaRevision } from '../revise-demo-cta.mjs';

const originalHash='3ce3687d080040ca24c50d40d4914ac40c75bb7596ec4b31bcde560a78cb0cfc';
const receipt={applicationCommit:'7b364c9ad693c35d00ca8edf1c428f19658b8d04',files:[{path:'demo-main-bgm.mp4',sha256:originalHash,durationSeconds:15,fullDecodeValidated:true}]};
const metadata={streams:[{codec_type:'video',codec_name:'h264',width:1080,height:1350,pix_fmt:'yuv420p',avg_frame_rate:'30/1',nb_frames:'450'},
  {codec_type:'audio',codec_name:'aac',sample_rate:'48000',channels:2,duration:'15'}],format:{duration:'15'}};
test('caption editing accepts only the exact previously verified BGM source',()=>{
  assert.doesNotThrow(()=>verifyCtaSource(receipt,originalHash));
  assert.throws(()=>verifyCtaSource(receipt,'a'.repeat(64)));
  for(const key of ['applicationCommit','files']){const bad=structuredClone(receipt);delete bad[key];assert.throws(()=>verifyCtaSource(bad,originalHash));}
  for(const change of [{fullDecodeValidated:false},{sha256:'b'.repeat(64)},{durationSeconds:3}]){
    const bad=structuredClone(receipt);Object.assign(bad.files[0],change);assert.throws(()=>verifyCtaSource(bad,originalHash));
  }
});
test('a revised video must keep the BGM packets and the complete X-compatible format',()=>{
  assert.doesNotThrow(()=>verifyCtaRevision(metadata,metadata,'original-audio','original-audio'));
  assert.throws(()=>verifyCtaRevision(metadata,metadata,'original-audio','changed-audio'));
  assert.throws(()=>verifyCtaRevision(metadata,metadata,'',''));
  for(const change of [{nb_frames:'449'},{avg_frame_rate:'24/1'},{width:720},{height:1080},{pix_fmt:'yuv444p'},{codec_name:'hevc'}]){
    const bad=structuredClone(metadata);Object.assign(bad.streams[0],change);assert.throws(()=>verifyCtaRevision(metadata,bad,'same','same'));
  }
  for(const change of [{channels:1},{sample_rate:'44100'},{codec_name:'mp3'},{duration:'14'}]){
    const bad=structuredClone(metadata);Object.assign(bad.streams[1],change);assert.throws(()=>verifyCtaRevision(metadata,bad,'same','same'));
  }
});
