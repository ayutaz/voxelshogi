import assert from 'node:assert/strict';
import test from 'node:test';
import {verifyBrowserStorageFlow} from '../verify-public-arena-storage.mjs';
const commit='a'.repeat(40),gameId='00000000-0000-4000-8000-000000000001';
function flow(){
  const first={httpStatus:201,packet:{schema:2,policy:'automatic-game-v2',applicationCommit:commit,gameId,requestId:'first',version:1,state:'progress',mode:'h-r',conditionsScope:'game-start',selectedAgents:{b:{kind:'human'},w:{kind:'easy',seed:42}},record:{ruleset_id:'voxelshogi-standard-v1',initial:'fixed initial',moves:['575565'],result:null,termination:null}},ack:{gameId,requestId:'first',version:1,status:'received_unverified'}};
  const last=structuredClone(first);Object.assign(last,{httpStatus:200});Object.assign(last.packet,{requestId:'last',version:3,state:'finished'});
  Object.assign(last.packet.record,{moves:['575565','535545'],result:{Win:{winner:'White',reason:'Resignation'}},termination:'Resignation'});
  Object.assign(last.ack,{requestId:'last',version:3});return{first,last};
}
test('proves a real human move, one shared game and acknowledged terminal update, without claiming Rust verification',()=>{
  const{first,last}=flow();verifyBrowserStorageFlow(first,last,commit);
});
test('rejects a fake success, unrelated game, changed conditions and wrong outcome',()=>{
  for(const change of [
    x=>{x.first.httpStatus=200;},x=>{x.last.packet.gameId='another';},
    x=>{x.last.ack.version=1;},x=>{x.last.packet.selectedAgents.w.seed=9;},
    x=>{x.last.packet.record.result.Win.winner='Black';},x=>{x.first.packet.applicationCommit='b'.repeat(40);},
  ]){const value=flow();change(value);assert.throws(()=>verifyBrowserStorageFlow(value.first,value.last,commit));}
});
