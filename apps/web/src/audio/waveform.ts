import type { SoundCue } from './cues';

export const SOUND_RATE = 22050;
export const SOUND_SECONDS: Record<SoundCue, number> = { move:0.08,capture:0.13,'capture-against':0.14,promotion:0.17,check:0.22,end:0.36,win:0.4,defeat:0.4 };

/** Original damped wood resonances, generated once per cue; no external audio assets. */
export function soundSamples(cue: SoundCue, variant: 'a' | 'b' = 'a'): Float32Array {
  const samples = new Float32Array(Math.round(SOUND_SECONDS[cue] * SOUND_RATE));
  const tau = Math.PI * 2, frequency = (cue === 'move' ? 780 : cue === 'capture-against' ? 420 : 550) * (variant === 'b' ? 1.2 : 1);
  const decay = cue.startsWith('capture') ? 38 : 72;
  let seed = 8173, previous = 0;
  for (let i=0;i<samples.length;i++) {
    const t=i/SOUND_RATE;
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    const noise=(seed>>>0)/2147483648-1, high=noise-previous*0.88;previous=noise;
    const attack=1-Math.exp(-t*3200);
    let value=attack*(0.3*Math.sin(tau*frequency*t)*Math.exp(-t*decay)+0.16*Math.sin(tau*frequency*2.13*t)*Math.exp(-t*110)+0.06*high*Math.exp(-t*230));
    const bell=(at:number,f:number,amp:number)=>{const u=t-at;return u<0?0:amp*(1-Math.exp(-u*600))*Math.exp(-u*20)*Math.sin(tau*f*u);};
    if(cue==='promotion')value+=bell(0.025,880,0.14)+bell(0.065,1174.66,0.1);
    if(cue==='check')value+=bell(0.01,659.25,0.15)+bell(0.1,783.99,0.13);
    if(cue==='end')value+=bell(0.01,523.25,0.12)+bell(0.12,523.25,0.1);
    if(cue==='win')value+=bell(0.01,523.25,0.12)+bell(0.1,659.25,0.12)+bell(0.2,783.99,0.1);
    if(cue==='defeat')value+=bell(0.01,523.25,0.12)+bell(0.1,440,0.1)+bell(0.2,349.23,0.09);
    // A smooth last 12ms avoids clicks when the bounded sample finishes.
    samples[i]=value*Math.min(1,(samples.length-1-i)/(SOUND_RATE*0.012));
  }
  return samples;
}
export function soundBuffer(context: AudioContext, cue: SoundCue): AudioBuffer {
  const data=soundSamples(cue),buffer=context.createBuffer(1,data.length,SOUND_RATE);
  buffer.getChannelData(0).set(data);return buffer;
}
