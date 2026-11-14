import { expect, it, vi } from 'vitest';
import { SoundPlayer, readSoundSettings, saveSoundSettings } from '../src/audio/player';
import type { PresentationEvent } from '../src/game/presentation';

const event = (id: number): PresentationEvent => ({ id:`1:${id}`, kind:'move', mover:'b', capture:false, promotion:false, check:false, result:null });
function fixture() {
  const sources: {start:ReturnType<typeof vi.fn>;stop:ReturnType<typeof vi.fn>;disconnect:ReturnType<typeof vi.fn>;onended:(()=>void)|null}[]=[];
  const gain={gain:{cancelScheduledValues:vi.fn(),setValueAtTime:vi.fn(),linearRampToValueAtTime:vi.fn(),value:0.35},connect:vi.fn(),disconnect:vi.fn()};
  const ctx={state:'running',currentTime:0, destination:{},resume:vi.fn(async()=>{}),close:vi.fn(async()=>{}),createGain:()=>gain,
    createBufferSource:()=>{const node={start:vi.fn(),stop:vi.fn(),connect:vi.fn(),disconnect:vi.fn(),onended:null};sources.push(node);return node;}};
  let clock=0;const factory=vi.fn(()=>ctx as unknown as AudioContext);
  const player=new SoundPlayer({enabled:true,volume:0.35},{context:factory,buffer:()=>({} as AudioBuffer),now:()=>clock});
  return {player,ctx,sources,factory,gain,tick:()=>{clock+=120;}};
}
it('is silent before gesture, deduplicates, throttles, and caps polyphony at two',async()=>{
  const f=fixture();f.player.handle(event(1),null);expect(f.factory).not.toHaveBeenCalled();
  await f.player.unlock();f.player.handle(event(2),null);expect(f.sources).toHaveLength(1);expect(f.sources[0]!.start).toHaveBeenCalledOnce();
  f.tick();f.player.handle(event(2),null);expect(f.sources).toHaveLength(1);
  f.player.handle(event(3),null);expect(f.sources).toHaveLength(2);
  f.player.handle(event(4),null);expect(f.sources).toHaveLength(2);
  f.tick();f.player.handle(event(5),null);expect(f.sources).toHaveLength(3);expect(f.sources[0]!.stop).toHaveBeenCalled();
  f.player.handle(event(1),null);expect(f.sources).toHaveLength(3);
});
it('mute and hidden tabs stop active sounds; clear/dispose never queue old events',async()=>{
  const f=fixture();await f.player.unlock();f.player.handle(event(1),null);
  f.player.configure({enabled:false,volume:0.35});expect(f.sources[0]!.stop).toHaveBeenCalled();f.tick();f.player.handle(event(2),null);expect(f.sources).toHaveLength(1);
  f.player.configure({enabled:true,volume:0.2});f.player.setVisible(false);f.tick();f.player.handle(event(3),null);expect(f.sources).toHaveLength(1);
  f.player.setVisible(true);expect(f.sources).toHaveLength(1);f.tick();f.player.handle(event(4),null);expect(f.sources).toHaveLength(2);
  f.player.handle({id:'1:5',kind:'clear'},null);expect(f.sources[1]!.stop).toHaveBeenCalled();
  f.player.dispose();expect(f.ctx.close).toHaveBeenCalledOnce();f.tick();f.player.handle(event(6),null);expect(f.sources).toHaveLength(2);
});
it('rejected/unsupported audio and a late test preview cannot interrupt the game',async()=>{
  const f=fixture();f.ctx.resume.mockRejectedValue(Error('blocked'));f.ctx.state='suspended';await expect(f.player.unlock()).resolves.toBeUndefined();
  expect(()=>f.player.handle(event(1),null)).not.toThrow();expect(f.sources).toHaveLength(0);
  let release!:()=>void;f.ctx.resume.mockImplementation(()=>new Promise(resolve=>{release=()=>{f.ctx.state='running';resolve();};}));
  const pending=f.player.preview();f.player.handle({id:'1:2',kind:'clear'},null);release();await pending;expect(f.sources).toHaveLength(0);
  const broken=new SoundPlayer({enabled:true,volume:0.35},{context:()=>{throw Error('unsupported');}});
  await expect(broken.unlock()).resolves.toBeUndefined();expect(()=>broken.handle(event(1),null)).not.toThrow();
});
it('keeps end cues even within the move cooldown',async()=>{
  const f=fixture();await f.player.unlock();f.player.handle(event(1),null);
  f.player.handle({id:'1:2',kind:'end',result:{kind:'draw',reason:'Repetition'}},null);expect(f.sources).toHaveLength(2);
});
it('validates local preferences and tolerates denied storage',()=>{
  const storage={getItem:vi.fn(()=>'{"enabled":false,"volume":0.6}'),setItem:vi.fn()};
  expect(readSoundSettings(storage)).toEqual({enabled:false,volume:0.6});saveSoundSettings({enabled:true,volume:0.4},storage);expect(storage.setItem).toHaveBeenCalledOnce();
  for(const text of ['oops','null','{"enabled":true,"volume":99}','{"enabled":"true","volume":0.4}']){storage.getItem.mockReturnValue(text);expect(readSoundSettings(storage)).toEqual({enabled:true,volume:0.35});}
  storage.getItem.mockImplementation(()=>{throw Error('denied');});storage.setItem.mockImplementation(()=>{throw Error('denied');});
  expect(readSoundSettings(storage)).toEqual({enabled:true,volume:0.35});expect(()=>saveSoundSettings({enabled:false,volume:0},storage)).not.toThrow();
});
