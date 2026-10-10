import test from 'node:test';
import assert from 'node:assert/strict';
import {matchingExecution,executionRows,executionNotices,requireInvestmentProtocol,canTransferOut} from '../src/utils/investmentInput.js';
const buy={id:'buy',kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW'};
const transfer={id:'move',kind:'TRANSFER',account_id:'cma',destination_account_id:'isa',currency:'KRW'};
const fx={id:'fx',kind:'EXCHANGE_IN',account_id:'us',currency:'USD'};
const context={portfolio_id:'p',cycle_id:'cycle',revision:3,step:buy,steps:[buy,transfer,fx]};
test('reviewed snapshot links the exact task without modifying actual amounts',()=>{
 const rows=[{kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW',quantity:7,price:9320}];
 const result=executionRows(rows,context,true);
 assert.deepEqual(result[0],{...rows[0],execution:{cycle_id:'cycle',step_id:'buy',revision:3}});
 assert.equal(rows[0].execution,undefined);
 assert.throws(()=>executionRows(rows,context,false),/먼저 확인/);
});
test('other matching tasks in one batch link uniquely; unrelated records stay independent',()=>{
 const rows=executionRows([{kind:'EXCHANGE_IN',account_id:'us',currency:'USD',usd_amount:400},{kind:'BUY',account_id:'other',asset_id:'bond',currency:'KRW'}],context,true);
 assert.equal(rows[0].execution.step_id,'fx');assert.equal(rows[1].execution,undefined);
 assert.throws(()=>executionRows([rows[1]],context,true),/계좌/);
});
test('ambiguous matches and excluded goals are never silently selected',()=>{
 const fact={kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW'};
 const ambiguous={...context,step:fx,steps:[buy,{...buy,id:'another'}]};
 assert.equal(matchingExecution(fact,ambiguous),undefined);
 assert.equal(matchingExecution(fact,{...context,step:{...buy,status:'EXCLUDED'},steps:[]}),undefined);
});
test('deposit and withdrawal notifications for an internal transfer share one direction',()=>{
 const outgoing={kind:'WITHDRAW',account_id:'cma',destination_account_id:'isa',external:false,event_date:'2026-10-10',krw_amount:180000};
 const incoming={kind:'DEPOSIT',account_id:'isa',source_account_id:'cma',external:false,event_date:'2026-10-10',krw_amount:180000};
 for(const row of [outgoing,incoming]){const result=executionNotices([row],context,true)[0];assert.deepEqual(result.execution,{cycle_id:'cycle',step_id:'move',revision:3});assert.equal(result.kind,row.kind);assert.equal(result.account_id,row.account_id);}
});
test('reflected-only cash cannot complete funding; cross-portfolio cash remains a deposit or withdrawal',()=>{
 assert.throws(()=>executionNotices([{kind:'WITHDRAW',account_id:'cma',destination_account_id:'isa',external:false,apply_cash:false}],context,true),/계좌/);
 assert.equal(executionNotices([{kind:'WITHDRAW',account_id:'cma',destination_account_id:'isa',external:false,cross_portfolio:true}],null,false)[0].execution,undefined);
});
test('old backend gates linked requests and preserves the exact frozen metadata',async()=>{
 const payload={trades:[{execution:{cycle_id:'c',step_id:'s',revision:1}}]},copy=structuredClone(payload);
 let calls=0;
 await requireInvestmentProtocol({getInvestmentCapabilities:()=>{calls++;}}, {trades:[{}]});assert.equal(calls,0);
 await assert.rejects(requireInvestmentProtocol({getInvestmentCapabilities:async()=>{throw new Error('404');}},payload),/요청은 보내지/);
 assert.deepEqual(payload,copy);
 await requireInvestmentProtocol({getInvestmentCapabilities:async()=>({investment_protocol:1})},payload);
});
test('tax accounts are never suggested as outgoing funding sources',()=>{
 for(const type of ['ISA','IRP','연금저축','퇴직연금','PENSION'])assert.equal(canTransferOut({account_type:type}),false);
 assert.equal(canTransferOut({account_type:'CMA'}),true);
});
