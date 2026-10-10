import test from 'node:test';
import assert from 'node:assert/strict';
import {investmentProgress, investmentStepProgress} from '../src/utils/investmentProgress.js';
const buy={id:'buy',kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW',target_quantity:20,depends_on:['fund']};
const fill=(id,quantity,other={})=>({id,step_id:'buy',kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW',quantity,ledger_status:'RECORDED',...other});
test('partial fills accumulate; duplicate and reversed results do not count',()=>{
 const progress=investmentStepProgress(buy,[fill('a',7),fill('a',7),fill('b',3),fill('void',50,{voided:true})]);
 assert.equal(progress.value,10);assert.equal(progress.remaining,10);assert.equal(progress.complete,false);
});
test('execution confirmed but not booked requires review instead of marking a purchase complete',()=>{
 const progress=investmentStepProgress(buy,[fill('confirmed',20,{ledger_status:'PENDING'})]);
 assert.equal(progress.value,0);assert.equal(progress.complete,false);assert.equal(progress.review,true);
});
test('records for a different account, asset, currency or operation are excluded',()=>{
 const progress=investmentStepProgress(buy,[fill('a',20,{account_id:'other'}),fill('b',20,{asset_id:'other'}),fill('c',20,{currency:'USD'}),fill('d',20,{kind:'SELL'})]);
 assert.equal(progress.value,0);assert.equal(progress.complete,false);
});
test('funding dependencies choose the next task and unrelated available tasks stay available',()=>{
 const fund={id:'fund',kind:'DEPOSIT',account_id:'cma',currency:'KRW',target_amount:100000};
 const independent={...buy,id:'other',depends_on:[]};
 let p=investmentProgress({steps:[fund,buy,independent],results:[]});
 assert.equal(p.current.step.id,'fund');assert.equal(p.steps[1].ready,false);assert.equal(p.steps[2].ready,true);
 p=investmentProgress({steps:[fund,buy],results:[{id:'cash',step_id:'fund',kind:'DEPOSIT',account_id:'cma',currency:'KRW',amount:100000,ledger_status:'RECORDED'}]});
 assert.equal(p.current.step.id,'buy');assert.equal(p.complete.length,1);
});
test('existing cash satisfies preparation without generating a new contribution',()=>{
 const p=investmentProgress({steps:[{id:'fund',kind:'DEPOSIT',account_id:'cma',currency:'KRW',target_amount:100000,satisfied_by_existing_cash:true},buy],results:[]});
 assert.equal(p.complete.length,1);assert.equal(p.current.step.id,'buy');assert.equal(p.complete[0].recorded.length,0);
});
test('overfills stay visible and invalid targets cannot silently complete',()=>{
 assert.equal(investmentStepProgress(buy,[fill('a',23)]).excess,3);
 assert.equal(investmentStepProgress({...buy,target_quantity:0},[]).review,true);
 assert.equal(investmentStepProgress({...buy,target_quantity:NaN},[]).complete,false);
});
test('missing dependency and paused or closed cycles cannot offer an executable task',()=>{
 assert.equal(investmentProgress({steps:[buy]}).current,undefined);
 for(const status of ['PAUSED','CLOSED']){const p=investmentProgress({status,steps:[{...buy,depends_on:[]}]});assert.equal(p.current,null);assert.equal(p.ready.length,0);}
});

test('excluding a prerequisite does not assert that cash has been prepared',()=>{
 const p=investmentProgress({steps:[{id:'fund',kind:'DEPOSIT',account_id:'cma',currency:'KRW',target_amount:100000,status:'EXCLUDED'},buy]});
 assert.equal(p.steps[1].ready,false);
});
