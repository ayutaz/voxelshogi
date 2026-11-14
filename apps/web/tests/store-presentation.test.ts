import { beforeAll, expect, it } from 'vitest';
import { loadWasm } from './loadWasm';
import { GameStore } from '../src/game/store';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm';
import type { PresentationEvent } from '../src/game/presentation';
beforeAll(loadWasm);

function smallPosition(extra: [number,number,number,string][],hands='-') {
  const layers=Array.from({length:9},()=>Array.from({length:9},()=>Array(9).fill('') as string[]));
  for(const [x,y,z,piece] of [[8,8,8,'K'],[0,0,0,'k'],...extra] as [number,number,number,string][])layers[z]![y]![8-x]=piece;
  const initial=layers.map(rows=>rows.map(row=>{let out='',empty=0;for(const piece of row){if(!piece)empty++;else{if(empty)out+=empty;empty=0;out+=piece;}}return out+(empty||'');}).join('/')).join('|')+` b ${hands} 1`;
  return new GameStore(Game.fromRecordJson(JSON.stringify({ruleset_id:'voxelshogi-standard-v1',initial,moves:[],result:null,termination:null})));
}

it('reports actual engine-accepted drop, promotion and check without reimplementing rules',()=>{
  for(const [store,move,expected] of [
    [smallPosition([],'P'),'P*555',{promotion:false,check:false,capture:false}],
    [smallPosition([[4,2,4,'P']]),'535525+',{promotion:true,check:false,capture:false}],
    // Moving onto layer I gives a rook plane attack; initially no coordinate is shared with 111.
    [smallPosition([[4,3,1,'R']]),'542541',{promotion:false,check:true,capture:false}],
  ] as const){const events:PresentationEvent[]=[];store.subscribePresentation(e=>events.push(e));expect(store.play(move)).toEqual({ok:true});expect(events).toHaveLength(1);expect(events[0]).toMatchObject({kind:'move',...expected});}
});

it('emits one accepted human/AI move, and none for illegal or stale responses', () => {
  const s = new GameStore(), events: PresentationEvent[] = [];
  s.subscribePresentation(e => events.push(e));
  const root = s.searchState();
  expect(s.play('555554').ok).toBe(false); expect(events).toHaveLength(0);
  expect(s.applyAiMove(root, '577567').ok).toBe(true);
  expect(events).toEqual([{ id: expect.any(String), kind: 'move', mover: 'b', capture: false, promotion: false, check: false, result: null }]);
  expect(s.applyAiMove(root, '577567').ok).toBe(false); expect(events).toHaveLength(1);
  s.snapshot(); s.snapshot(); expect(events).toHaveLength(1);
});
it('keeps reset/import/jumps silent and marks only explicit single-step forward', () => {
  const s = new GameStore(), events: PresentationEvent[] = [];
  s.subscribePresentation(e => events.push(e));
  s.play('577567'); const record = s.exportRecord(); s.goto(0); s.stepForward();
  expect(events.map(e => e.kind)).toEqual(['move', 'clear', 'clear', 'forward']);
  s.goto(0); s.undo(); s.newGame(); s.importRecord(record);
  expect(events.slice(4).every(e => e.kind === 'clear')).toBe(true);
  expect(new Set(events.map(e => e.id)).size).toBe(events.length);
});
it('describes capture from the board before the accepted move and survives observer failure', () => {
  const layers = Array.from({ length: 9 }, () => Array.from({ length: 9 }, () => Array(9).fill('') as string[]));
  layers[8]![8]![0] = 'K'; layers[0]![0]![8] = 'k';
  layers[4]![4]![4] = 'R'; layers[4]![3]![4] = 'p';
  const initial = layers.map(rows => rows.map(row => { let out='',empty=0; for(const piece of row){if(!piece)empty++;else{if(empty)out+=empty;empty=0;out+=piece;}}return out+(empty||''); }).join('/')).join('|')+' b - 1';
  const s = new GameStore(Game.fromRecordJson(JSON.stringify({ ruleset_id:'voxelshogi-standard-v1', initial, moves:[], result:null, termination:null })));
  const events: PresentationEvent[] = []; s.subscribePresentation(() => { throw Error('audio failure'); }); s.subscribePresentation(e => events.push(e));
  expect(s.play('555545')).toEqual({ ok:true });
  expect(events[0]).toMatchObject({ kind:'move', capture:true, mover:'b' });
  s.resign(); s.resign();
  expect(events.filter(e=>e.kind==='end')).toHaveLength(1);
});
