import {expect,it} from 'vitest';
import {PerspectiveCamera} from 'three';
import {layerLabelPosition} from '../src/renderer/layer-label-position';
function camera(distance:number){const c=new PerspectiveCamera(90,1,.1,1000);c.position.set(0,0,distance);c.lookAt(0,0,0);c.updateMatrixWorld();return c;}
it('projects layer labels with a constant readable box, using independent 90-degree camera geometry',()=>{
  const c=camera(30);
  // Front-edge depth is 4.5: camera distance 25.5, half viewport 200.
  const center=layerLabelPosition(c,{width:400,height:400},4);
  expect(center.x).toBeCloseTo(182-1200/25.5,8);expect(center.y).toBe(190);
  expect(layerLabelPosition(c,{width:400,height:400},0).y).toBeCloseTo(190+160/3,8);
  expect(layerLabelPosition(c,{width:400,height:400},8).y).toBeCloseTo(190-160/3,8);
});
it('keeps text entirely inside the canvas when zooming would otherwise clip its anchor',()=>{
  const c=camera(10),size={width:400,height:400};
  expect(layerLabelPosition(c,size,0)).toEqual({x:4,y:376});
  expect(layerLabelPosition(c,size,8)).toEqual({x:4,y:4});
});
