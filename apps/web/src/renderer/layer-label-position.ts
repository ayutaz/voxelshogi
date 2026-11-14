import {Vector3,type Camera} from 'three';

/** CSS-pixel labels stay legible while their anchors follow the actual camera. */
export function layerLabelPosition(camera:Camera,size:{width:number;height:number},z:number){
  const point=new Vector3(-6,(z-4)*1.7,4.5).project(camera);
  const clamp=(value:number,max:number)=>Math.max(4, Math.min(max, value));
  return {x:clamp((point.x*.5+.5)*size.width-18,size.width-40),
    y:clamp((-.5*point.y+.5)*size.height-10,size.height-24)};
}
