import type { Color } from '../game/model';
import type { PresentationEvent } from '../game/presentation';
import { cueFor, type SoundCue } from './cues';
import { soundBuffer } from './waveform';

export interface SoundSettings { enabled: boolean; volume: number }
const DEFAULT: SoundSettings = { enabled:true, volume:0.35 }, KEY='voxelshogi:sound:v1';
type StoragePort = Pick<Storage,'getItem'|'setItem'>;
export function readSoundSettings(storage?: StoragePort): SoundSettings {
  try { const value=JSON.parse((storage??globalThis.localStorage).getItem(KEY)??'null');
    if(typeof value?.enabled==='boolean'&&typeof value.volume==='number'&&Number.isFinite(value.volume)&&value.volume>=0&&value.volume<=1)return {enabled:value.enabled,volume:value.volume};
  } catch { /* Private browsing or unavailable storage keeps usable local defaults. */ }
  return {...DEFAULT};
}
export function saveSoundSettings(settings: SoundSettings, storage?: StoragePort): void {
  try { (storage??globalThis.localStorage).setItem(KEY,JSON.stringify(settings)); } catch { /* Optional persistence. */ }
}
interface Dependencies { context?:()=>AudioContext; buffer?:(context:AudioContext,cue:SoundCue)=>AudioBuffer; now?:()=>number }
export class SoundPlayer {
  private context: AudioContext | null = null;
  private gain: GainNode | null = null;
  private buffers = new Map<SoundCue,AudioBuffer>();
  private active = new Set<AudioBufferSourceNode>();
  private seen = new Map<string,number>();
  private visible = true;
  private disposed = false;
  private generation = 0;
  private lastMove = -Infinity;
  constructor(private settings:SoundSettings,private dependencies:Dependencies={}) {}

  async unlock():Promise<void> {
    if(this.disposed||!this.settings.enabled||!this.visible)return;
    try {
      if(!this.context||this.context.state==='closed'||!this.gain) {
        this.context=(this.dependencies.context??(()=>new AudioContext({latencyHint:'interactive'})))();
        this.gain=this.context.createGain();this.gain.gain.value=this.settings.volume;this.gain.connect(this.context.destination);this.buffers.clear();
      }
      if(this.context.state!=='running')await this.context.resume();
    } catch { /* Audio is optional; never reject a game action. */ }
  }
  configure(settings:SoundSettings):void {
    this.settings={enabled:settings.enabled,volume:Math.max(0,Math.min(1,Number.isFinite(settings.volume)?settings.volume:0.35))};
    if(!settings.enabled||this.settings.volume===0)this.stop();
    this.setGain();
  }
  setVisible(value:boolean):void { this.visible=value;if(!value)this.stop();this.setGain(); }
  private setGain():void {
    if(!this.gain||!this.context)return;
    try {const p=this.gain.gain,t=this.context.currentTime;p.cancelScheduledValues(t);p.setValueAtTime(p.value,t);p.linearRampToValueAtTime(this.visible&&this.settings.enabled?this.settings.volume:0,t+0.012);}catch{/* interrupted context */}
  }
  private stop():void {
    this.generation++;
    if(this.gain&&this.context){try{const p=this.gain.gain,t=this.context.currentTime;p.cancelScheduledValues(t);p.setValueAtTime(p.value,t);p.linearRampToValueAtTime(0,t+0.012);}catch{/* interrupted context */}}
    for(const source of this.active){try{source.stop((this.context?.currentTime??0)+0.012);}catch{/* already ended */}}
    this.active.clear();
  }
  handle(event:PresentationEvent,human:Color|null):void {
    const split=event.id.lastIndexOf(':'),owner=event.id.slice(0,split),sequence=Number(event.id.slice(split+1));
    if(!Number.isSafeInteger(sequence)||sequence<1||sequence<=(this.seen.get(owner)??0))return;
    this.seen.set(owner,sequence);
    if(event.kind==='clear'){this.stop();return;}
    const cue=cueFor(event,human);if(cue)this.play(cue);
  }
  private play(cue:SoundCue):void {
    const context=this.context;
    if(this.disposed||!this.visible||!this.settings.enabled||this.settings.volume===0||context?.state!=='running'||!this.gain)return;
    const now=(this.dependencies.now??(()=>performance.now()))(),ending=['end','win','defeat'].includes(cue);
    if(!ending&&now-this.lastMove<120)return;
    try {
      let buffer=this.buffers.get(cue);if(!buffer){buffer=(this.dependencies.buffer??soundBuffer)(context,cue);this.buffers.set(cue,buffer);}
      if(ending)this.stop();
      if(this.active.size>=2){const oldest=this.active.values().next().value!;try{oldest.stop();}catch{/* already ended */}this.active.delete(oldest);}
      this.setGain();
      const source=context.createBufferSource();source.buffer=buffer;source.connect(this.gain);
      source.onended=()=>{this.active.delete(source);source.disconnect();};
      try{source.start();this.active.add(source);}catch{source.disconnect();return;}
      if(!ending)this.lastMove=now;
    } catch { /* Buffer/device failures never affect the game or its saving. */ }
  }
  async preview():Promise<void> {
    const generation=this.generation;await this.unlock();if(generation===this.generation)this.play('move');
  }
  dispose():void {
    this.disposed=true;this.stop();this.buffers.clear();this.seen.clear();
    try {void this.context?.close().catch(()=>{});this.gain?.disconnect();}catch{/* already closed */}
    this.context=null;this.gain=null;
  }
}
