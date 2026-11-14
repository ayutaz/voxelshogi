import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { SOUND_RATE, SOUND_SECONDS, soundSamples } from '../apps/web/src/audio/waveform.ts';

assert.equal(process.platform,'linux','Sound sample rendering belongs on Linux');
const out=resolve(process.argv[2]);mkdirSync(out,{recursive:true});const files=[];
for(const [cue,variant] of [...Object.keys(SOUND_SECONDS).map(c=>[c,'a']),['move','b'],['capture','b']]) {
  const samples=soundSamples(cue,variant),wav=Buffer.alloc(44+samples.length*2);
  let peak=0,sum=0;for(const value of samples){assert.ok(Number.isFinite(value));peak=Math.max(peak,Math.abs(value));sum+=value*value;}
  assert.ok(peak>0.05&&peak<0.85);assert.ok(Math.sqrt(sum/samples.length)>0.01);assert.ok(samples[0]===0&&samples.at(-1)===0);
  wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(SOUND_RATE,24);wav.writeUInt32LE(SOUND_RATE*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(samples.length*2,40);
  for(let i=0;i<samples.length;i++)wav.writeInt16LE(Math.round(samples[i]*32767),44+i*2);
  const path=`${cue}-${variant}.wav`;writeFileSync(join(out,path),wav,{flag:'wx'});files.push({cue,variant,path,bytes:wav.length,seconds:samples.length/SOUND_RATE,peakDb:20*Math.log10(peak),sha256:createHash('sha256').update(wav).digest('hex')});
}
const selectedBytes=files.filter(f=>f.variant==='a').reduce((n,f)=>n+f.bytes,0);assert.ok(selectedBytes<100*1024);
const proof={schema:1,kind:'voxelshogi-original-game-sounds',rate:SOUND_RATE,channels:1,sourceLicense:'Apache-2.0',thirdPartySamples:false,selectedVariant:'a',selectedPcmWavBytes:selectedBytes,browserDelivery:'same deterministic PCM generated lazily from bundled source; no audio network requests',files};
writeFileSync(join(out,'samples.json'),JSON.stringify(proof,null,2)+'\n',{flag:'wx'});
writeFileSync(join(out,'preview.html'),'<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>VoxelShogi SE試聴</title><style>body{font-family:system-ui;background:#102025;color:#eef6f5;margin:28px;max-width:780px}article{padding:12px;border-bottom:1px solid #466}audio{width:100%}h2{font-size:16px}</style><h1>VoxelShogi SE試聴</h1><p>移動・捕獲はA/Bの2案。Aを採用し、捕獲を少し低く長くしています。各プレイヤーで音量を調整できます。</p>'+files.map(f=>`<article><h2>${f.cue} · ${f.variant.toUpperCase()}（${Math.round(f.seconds*1000)}ms）</h2><audio controls preload="none" src="${f.path}"></audio></article>`).join('')+'</html>',{flag:'wx'});
console.log(JSON.stringify(proof));
