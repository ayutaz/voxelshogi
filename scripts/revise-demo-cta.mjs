// Edit only the closing caption band of the already reviewed BGM video, on Linux.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const SOURCE_HASH='3ce3687d080040ca24c50d40d4914ac40c75bb7596ec4b31bcde560a78cb0cfc';
export function verifyCtaSource(receipt, hash) {
  assert.equal(hash,SOURCE_HASH,'use the reviewed fifteen-second BGM video');
  assert.equal(receipt.applicationCommit,'7b364c9ad693c35d00ca8edf1c428f19658b8d04');
  const file=receipt.files.find(f=>f.path==='demo-main-bgm.mp4');
  assert.equal(file.sha256,SOURCE_HASH);assert.equal(file.durationSeconds,15);assert.equal(file.fullDecodeValidated,true);
}
export function verifyCtaRevision(source, output, before, after) {
  assert.ok(before && before===after,'BGM compressed packets must stay identical');
  for(const p of [source,output]) {
    const videos=p.streams.filter(s=>s.codec_type==='video');assert.equal(videos.length,1);
    const v=videos[0];
    for(const [key,value] of Object.entries({codec_name:'h264',width:1080,height:1350,pix_fmt:'yuv420p',avg_frame_rate:'30/1',nb_frames:'450'}))assert.equal(v[key],value,key);
    const audios=p.streams.filter(s=>s.codec_type==='audio');assert.equal(audios.length,1);
    const a=audios[0];assert.equal(a.codec_name,'aac');assert.equal(a.channels,2);assert.equal(a.sample_rate,'48000');
    assert.ok(Math.abs(Number(a.duration)-15)<0.05);assert.ok(Math.abs(Number(p.format.duration)-15)<0.05);
  }
}
function main() {
  assert.equal(process.platform,'linux','Video editing and analysis run on Linux CI');
  const source=resolve(process.argv[2]),out=resolve(process.argv[3]);assert.notEqual(source,out);mkdirSync(out,{recursive:true});
  const input=join(source,'demo-main-bgm.mp4'),output=join(out,'demo-main-bgm.mp4');
  const digest=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
  const original=JSON.parse(readFileSync(join(source,'bgm-receipt.json')));verifyCtaSource(original,digest(input));
  const run=(bin,args,options={})=>execFileSync(bin,args,{encoding:'utf8',maxBuffer:4*1024*1024,...options});
  const probe=p=>JSON.parse(run('ffprobe',['-v','error','-show_streams','-show_format','-of','json',p]));
  const audioHash=p=>run('ffmpeg',['-v','error','-i',p,'-map','0:a:0','-c:a','copy','-f','hash','-hash','sha256','-']).trim();
  const font='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc';readFileSync(font);
  const note='学習済みS・INT8（重み）';writeFileSync(join(out,'cta-note.txt'),note+'\n',{flag:'wx'});
  // Both old and replacement text lie inside the original solid footer, below the URL.
  const filter="drawbox=x=0:y=1240:w=iw:h=90:color=0x10191c:t=fill:enable='gte(t,11)',"+
    `drawtext=fontfile=${font}:textfile=cta-note.txt:x=(w-text_w)/2:y=1260:fontsize=30:fontcolor=white:borderw=3:bordercolor=0x0f1115:enable='gte(t,11)'`;
  run('ffmpeg',['-v','error','-y','-i',input,'-map','0:v:0','-map','0:a:0','-vf',filter,
    '-c:v','libx264','-preset','fast','-crf','16','-profile:v','high','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',output],{cwd:out});
  verifyCtaRevision(probe(input),probe(output),audioHash(input),audioHash(output));
  run('ffmpeg',['-v','error','-xerror','-i',output,'-map','0:v:0','-map','0:a:0','-f','null','-']);
  const compare = filters => {
    const r=spawnSync('ffmpeg',['-hide_banner','-i',input,'-i',output,'-filter_complex',filters,'-an','-f','null','-'],{encoding:'utf8',maxBuffer:4*1024*1024});
    assert.equal(r.status,0,r.stderr);const value=Number([...r.stderr.matchAll(/All:([0-9.]+)/g)].at(-1)?.[1]);assert.ok(Number.isFinite(value));return value;
  };
  const mask='drawbox=x=0:y=1240:w=iw:h=90:color=black:t=fill';
  const outsideCaptionSsim=compare(`[0:v]${mask}[a];[1:v]${mask}[b];[a][b]ssim`);
  assert.ok(outsideCaptionSsim>=0.995,'avoid degrading the previously reviewed game and URL');
  const openingSsim=compare('[0:v]trim=end_frame=330,setpts=PTS-STARTPTS[a];[1:v]trim=end_frame=330,setpts=PTS-STARTPTS[b];[a][b]ssim');
  assert.ok(openingSsim>=0.995,'opening and controls must retain their reviewed appearance');
  const closingCaptionSsim=compare('[0:v]trim=start_frame=330,crop=1080:90:0:1240,setpts=PTS-STARTPTS[a];[1:v]trim=start_frame=330,crop=1080:90:0:1240,setpts=PTS-STARTPTS[b];[a][b]ssim');
  assert.ok(closingCaptionSsim<0.999,'closing caption must actually change');
  const files=['demo-main-bgm.mp4'];
  for(const seconds of [0,3,10.8,10.96,11,11.2,14.9]) {
    const file=`review-${String(seconds).replace('.','-')}.png`;
    run('ffmpeg',['-v','error','-y','-ss',String(seconds),'-i',output,'-frames:v','1',join(out,file)]);files.push(file);
  }
  assert.ok(readFileSync(output).length<32*1024*1024,'keep the fifteen-second delivery small');
  const receipt={schema:1,kind:'voxelshogi-closing-caption-revision',editCommit:process.env.GITHUB_SHA,
    applicationCommit:original.applicationCommit,sourceRun:43620484463,sourceSha256:SOURCE_HASH,
    removed:'／申請・ログイン不要',replacementNote:note,editedSeconds:[11,15],editedRectangle:{x:0,y:1240,width:1080,height:90},
    audioPacketsUnchanged:true,audioPacketHash:audioHash(output),videoReencoded:true,gameRerecorded:false,
    outsideCaptionSsim,openingSsim,closingCaptionSsim,fullDecodeValidated:true,visualReviewComplete:false,
    japaneseFontSha256:digest(font),files:files.map(path=>({path,bytes:readFileSync(join(out,path)).length,sha256:digest(join(out,path))}))};
  writeFileSync(join(out,'cta-receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(receipt));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)main();
