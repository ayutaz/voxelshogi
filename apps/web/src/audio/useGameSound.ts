import { useEffect, useRef, useState } from 'react';
import type { GameStore } from '../game/store';
import type { Color } from '../game/model';
import { readSoundSettings, saveSoundSettings, SoundPlayer, type SoundSettings } from './player';

export function useGameSound(store:GameStore,mode:'h-r'|'r-h'|'r-r') {
  const [settings,setSettings]=useState(()=>readSoundSettings());
  const latest=useRef(settings),human=useRef<Color|null>(null),player=useRef<SoundPlayer|null>(null);
  latest.current=settings;human.current=mode==='h-r'?'b':mode==='r-h'?'w':null;
  useEffect(()=>{
    const instance=new SoundPlayer(latest.current);player.current=instance;
    const unsubscribe=store.subscribePresentation(event=>instance.handle(event,human.current));
    const visibility=()=>instance.setVisible(document.visibilityState!=='hidden');visibility();
    const gesture=()=>{void instance.unlock();};
    const key=(event:KeyboardEvent)=>{if(event.key==='Enter'||event.key===' ')gesture();};
    document.addEventListener('click',gesture,true);document.addEventListener('keydown',key,true);document.addEventListener('visibilitychange',visibility);
    return ()=>{unsubscribe();document.removeEventListener('click',gesture,true);document.removeEventListener('keydown',key,true);document.removeEventListener('visibilitychange',visibility);instance.dispose();if(player.current===instance)player.current=null;};
  },[store]);
  const configure=(value:SoundSettings)=>{latest.current=value;setSettings(value);player.current?.configure(value);saveSoundSettings(value);if(value.enabled)void player.current?.unlock();};
  return {settings,toggle:()=>configure({...latest.current,enabled:!latest.current.enabled}),
    setVolume:(volume:number)=>configure({...latest.current,volume}),preview:()=>{void player.current?.preview();}};
}
