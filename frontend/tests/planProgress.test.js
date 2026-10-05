import test from 'node:test';
import assert from 'node:assert/strict';
import {planProgress,planCandidates} from '../src/utils/planProgress.js';

test('actual linked quantities and FX amounts expose both partial completion and excess',()=>{
  const plan={cutoff:8,payload:{trade_plan:[{account_id:'a',asset_id:'s',type:'BUY',qty:3}]},links:[{line_no:0,quantity:2,price:10,currency:'USD',exchange_rate:1400},{line_no:1,quantity:100}]};
  assert.deepEqual({...planProgress(plan,0),links:[]},{links:[],quantity:2,amount:28000,remaining:1,excess:0});
  plan.links.push({line_no:0,quantity:2,price:9000,currency:'KRW'});
  assert.equal(planProgress(plan,0).excess,1);
  assert.equal(planProgress(plan,0).remaining,0);
});
test('only matching account asset direction and post-save trades become candidates',()=>{
  const plan={cutoff:8,payload:{trade_plan:[{account_id:'a',asset_id:'s',type:'BUY'}]}};
  const t={id:'new',account_id:'a',asset_id:'s',trade_type:'BUY',trade_sequence:9};
  assert.deepEqual(planCandidates(plan,0,[t,{...t,trade_sequence:8},{...t,account_id:'other'},{...t,trade_type:'SELL'}]),[t]);
});
