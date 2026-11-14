// Original procedural instrumental; no third-party recordings or trained model.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function verifyAudioVideo(source, output, before, after, seconds) {
  assert.ok(before && before === after, 'compressed video packets must stay identical');
  const v = source.streams.find(s => s.codec_type === 'video');
  const videos = output.streams.filter(s => s.codec_type === 'video');
  assert.equal(videos.length, 1);
  for (const key of ['codec_name', 'width', 'height', 'avg_frame_rate', 'nb_frames']) assert.equal(videos[0][key], v[key], key);
  assert.equal(Number(videos[0].nb_frames), seconds * 30);
  const audio = output.streams.filter(s => s.codec_type === 'audio');
  assert.equal(audio.length, 1); assert.equal(audio[0].codec_name, 'aac');
  assert.equal(audio[0].channels, 2); assert.equal(audio[0].sample_rate, '48000');
  assert.ok(Math.abs(Number(audio[0].duration) - seconds) < 0.05);
  assert.ok(Math.abs(Number(output.format.duration) - seconds) < 0.05);
}

function compose() {
  const rate = 48000, count = 15 * rate, left = new Float64Array(count), right = new Float64Array(count);
  const beat = 60 / 128, tau = Math.PI * 2, hz = midi => 440 * 2 ** ((midi - 69) / 12);
  let seed = 73529;
  const noise = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return (seed >>> 0) / 2147483648 - 1; };
  const add = (at, duration, sample, pan = 0, gain = 1) => {
    const start = Math.round(at * rate), end = Math.min(count, start + Math.round(duration * rate));
    for (let i = start; i < end; i++) {
      const t = (i - start) / rate, x = sample(t) * gain;
      left[i] += x * Math.sqrt((1 - pan) / 2); right[i] += x * Math.sqrt((1 + pan) / 2);
    }
  };
  const pluck = (at, note, gain, pan) => {
    const f = hz(note);
    const tone = t => (1 - Math.exp(-t * 1100)) * Math.exp(-t * 9) * (Math.sin(tau * f * t) + 0.24 * Math.sin(tau * f * 2 * t) + 0.08 * Math.sin(tau * f * 3 * t));
    add(at, 0.6, tone, pan, gain); add(at + beat * 0.75, 0.6, tone, -pan, gain * 0.18);
  };
  const roots = [38, 38, 34, 34, 41, 41, 36, 38];
  const chords = [[62,65,69,72], [62,65,69,72], [58,62,65,69], [58,62,65,69], [60,65,69,72], [60,65,69,72], [60,64,67,72], [62,65,69,74]];
  for (let bar = 0; bar < 8; bar++) {
    const start = bar * beat * 4;
    for (const note of chords[bar]) {
      const f = hz(note - 12);
      add(start, beat * 4 + 0.15, t => {
        const env = Math.min(1,t/0.09) * Math.min(1,Math.max(0,(beat * 4 + 0.15-t)/0.3));
        return env * (Math.sin(tau*f*t)+0.28*Math.sin(tau*f*1.003*t));
      }, note % 2 ? 0.45 : -0.45, 0.025);
    }
    for (let step = 0; step < 8; step++) {
      const at = start + step * beat / 2;
      pluck(at, chords[bar][[0,2,1,3,2,1,3,2][step]] + (bar >= 4 ? 12 : 0), step % 2 ? 0.075 : 0.105, step % 2 ? 0.3 : -0.3);
      add(at, 0.065, t => noise() * Math.exp(-t * 85) * Math.min(1,t*2200), step % 2 ? 0.45 : -0.45, step % 2 ? 0.018 : 0.026);
      if (step % 2 === 0) {
        const f = hz(roots[bar] + (step === 6 ? 12 : 0));
        add(at, beat * 0.86, t => Math.min(1,t*300) * Math.exp(-t*7) * (Math.sin(tau*f*t)+0.18*Math.sin(tau*f*2*t)), 0, 0.22);
      }
    }
    for (let pulse = 0; pulse < 4; pulse++) {
      const at = start + pulse * beat;
      add(at, 0.23, t => Math.sin(tau*(49*t+6.3*(1-Math.exp(-t*24)))) * Math.exp(-t*22) * Math.min(1,t*1800), 0, 0.3);
      if (pulse % 2 === 1) add(at, 0.15, t => (noise()*0.8+Math.sin(tau*185*t)*0.2)*Math.exp(-t*30)*Math.min(1,t*1800), 0.08, 0.09);
    }
  }
  for (const [i,n] of [74,77,81].entries()) pluck(13.125 + i*0.06,n,0.1,0);
  let peak = 0;
  for (let i = 0; i < count; i++) {
    const t=i/rate, fade=Math.min(1,t/0.008)*Math.min(1,Math.max(0,(15-t)/0.65));
    left[i]=Math.tanh(left[i])*fade;right[i]=Math.tanh(right[i])*fade;
    peak=Math.max(peak,Math.abs(left[i]),Math.abs(right[i]));
  }
  const wav = Buffer.alloc(44 + count * 4);
  wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);
  wav.writeUInt16LE(1,20);wav.writeUInt16LE(2,22);wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*4,28);
  wav.writeUInt16LE(4,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(count*4,40);
  for(let i=0;i<count;i++){wav.writeInt16LE(Math.round(left[i]/peak*0.78*32767),44+i*4);wav.writeInt16LE(Math.round(right[i]/peak*0.78*32767),46+i*4);}
  return wav;
}

function main() {
  assert.equal(process.platform,'linux','Music rendering and video validation run on Linux');
  const source=resolve(process.argv[2]),out=resolve(process.argv[3]);
  assert.notEqual(source,out);mkdirSync(out,{recursive:true});
  const run=(bin,args)=>execFileSync(bin,args,{encoding:'utf8',maxBuffer:4*1024*1024});
  const digest=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
  const probe=p=>JSON.parse(run('ffprobe',['-v','error','-show_streams','-show_format','-of','json',p]));
  const videoHash=p=>run('ffmpeg',['-v','error','-i',p,'-map','0:v:0','-c:v','copy','-f','hash','-hash','sha256','-']).trim();
  const receipt=JSON.parse(readFileSync(join(source,'receipt.json')));
  assert.equal(receipt.appCommit,'7b364c9ad693c35d00ca8edf1c428f19658b8d04');assert.equal(receipt.candidate,false);
  assert.equal(receipt.fullDecodeValidated,true);assert.equal(receipt.humanModelReplyVerified,true);
  const expected={ 'demo-main.mp4':'da0279fa9fe0fc208881c9e05e6ac12d3bb86ade1fbbbe9c9b793aabc6d87e04', 'hook-a.mp4':'5dde8830eac92a7b200e60d9fbbc1c48abdc3db75d10ab2610f7f6c209d07324', 'hook-b.mp4':'db0655886d6551f7ce250b135db5284460656a54ffea1b18a3094a04718eb60a' };
  for(const [file,hash] of Object.entries(expected)){assert.equal(digest(join(source,file)),hash);assert.equal(receipt.files.find(f=>f.path===file)?.sha256,hash);}
  const wav=join(out,'original-demo-bgm.wav');writeFileSync(wav,compose(),{flag:'wx',mode:0o600});
  const audioStats = input => {
    const r=spawnSync('ffmpeg',['-hide_banner','-i',input,'-map','0:a:0','-af','loudnorm=I=-18:TP=-2:LRA=7:print_format=json','-f','null','-'],{encoding:'utf8',maxBuffer:4*1024*1024});
    assert.equal(r.status,0,r.stderr);return JSON.parse(r.stderr.slice(r.stderr.lastIndexOf('{')));
  };
  const measured=audioStats(wav);
  const normalize=`loudnorm=I=-18:TP=-2:LRA=7:measured_I=${measured.input_i}:measured_TP=${measured.input_tp}:measured_LRA=${measured.input_lra}:measured_thresh=${measured.input_thresh}:offset=${measured.target_offset}:linear=true`;
  const files=[];
  for(const [file,seconds] of [['demo-main.mp4',15],['hook-a.mp4',3],['hook-b.mp4',3]]){
    const input=join(source,file),output=join(out,file.replace('.mp4','-bgm.mp4'));
    run('ffmpeg',['-v','error','-i',input,'-i',wav,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-af',`${normalize},afade=t=out:st=${seconds-0.15}:d=0.15`,'-t',String(seconds),'-movflags','+faststart',output]);
    verifyAudioVideo(probe(input),probe(output),videoHash(input),videoHash(output),seconds);
    run('ffmpeg',['-v','error','-xerror','-i',output,'-map','0:v:0','-map','0:a:0','-f','null','-']);
    const stats=audioStats(output),lufs=Number(stats.input_i),peak=Number(stats.input_tp);
    assert.ok(Number.isFinite(lufs)&&lufs>-40&&lufs<-10,'audible bounded music required');
    assert.ok(Number.isFinite(peak)&&peak<=-1,'no decoded audio clipping');
    if(seconds===15)assert.ok(Math.abs(lufs+18)<1.5,'main mix loudness');
    files.push({path:file.replace('.mp4','-bgm.mp4'),bytes:readFileSync(output).length,sha256:digest(output),durationSeconds:seconds,videoPacketsUnchanged:true,fullDecodeValidated:true,loudnessLufs:lufs,truePeakDb:peak});
  }
  const result={schema:1,kind:'voxelshogi-original-demo-bgm',applicationCommit:receipt.appCommit,sourceVideoRun:43611290885,music:{style:'light electronic instrumental',bpm:128,bars:8,seconds:15,sampleRate:48000,channels:2,composition:'original procedural score',thirdPartySamples:false,sourceLicense:'Apache-2.0',targetLufs:-18,targetTruePeakDb:-2,wavSha256:digest(wav)},files};
  writeFileSync(join(out,'bgm-receipt.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log(JSON.stringify(result));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)main();
