import test from 'node:test';
import assert from 'node:assert/strict';
import {matchingExecution,executionRows,executionNotices,requireInvestmentProtocol,canTransferOut,executionReferencePrice,seedExecutionPrice} from '../src/utils/investmentInput.js';
const buy={id:'buy',kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW'};
const transfer={id:'move',kind:'TRANSFER',account_id:'cma',destination_account_id:'isa',currency:'KRW'};
const fx={id:'fx',kind:'EXCHANGE_IN',account_id:'us',currency:'USD'};
const context={portfolio_id:'p',cycle_id:'cycle',revision:3,step:buy,steps:[buy,transfer,fx]};
test('reviewed snapshot links the exact task without modifying actual amounts',()=>{
 const rows=[{kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW',quantity:7,price:9320}];
 const result=executionRows(rows,context,true);
 assert.deepEqual(result[0],{...rows[0],execution:{cycle_id:'cycle',step_id:'buy',revision:3}});
 assert.equal(rows[0].execution,undefined);
 assert.deepEqual(executionRows(rows,context),result);
});
test('tab 5 records remain independent; task input refuses unrelated rows before any write',()=>{
 const unrelated={kind:'BUY',account_id:'other',asset_id:'bond',currency:'KRW',quantity:3,price:100};
 assert.deepEqual(executionRows([unrelated],null),[unrelated]);
 assert.throws(()=>executionRows([unrelated],context),/선택한 작업/);
 assert.throws(()=>executionRows([{kind:'EXCHANGE_IN',account_id:'us',currency:'USD'}],context),/선택한 작업/);
 assert.throws(()=>executionRows([{kind:'BUY',account_id:'isa',asset_id:'bond',currency:'KRW'},unrelated],context),/선택한 작업/);
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
 for(const row of [outgoing,incoming]){const result=executionNotices([row],{...context,step:transfer})[0];assert.deepEqual(result.execution,{cycle_id:'cycle',step_id:'move',revision:3});assert.equal(result.kind,row.kind);assert.equal(result.account_id,row.account_id);}
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

test('execution default prices use native USD or matching KRW quotes, then plan price',()=>{
 const us={...buy,asset_id:'vt',currency:'USD',estimated_price:'90'};
 assert.equal(executionReferencePrice(us,{vt:140000},[{id:'vt',price_usd:101.25}],1400),101.25);
 assert.equal(executionReferencePrice(us,{vt:140000},[],1400),100);
 assert.equal(executionReferencePrice(us,{vt:140000},[],0),90);
 assert.equal(executionReferencePrice(buy,{bond:9320},[],1400),9320);
 assert.equal(executionReferencePrice({...buy,estimated_price:'9000'},{bond:NaN}),9000);
 assert.equal(executionReferencePrice({...buy,estimated_price:Infinity},{}),0);
 assert.equal(executionReferencePrice(fx,{us:100}),0);
});

test('execution price seeding preserves edited/imported/unrelated and uncertain drafts',()=>{
 const empty={accountId:'isa',assetId:'bond',quantity:3,price:0};
 const edited={...empty,price:9300};
 const imported={...empty,importSource:'NAMUH_KAKAO'};
 const unrelated={...empty,assetId:'other'};
 const rows=[empty,edited,imported,unrelated];
 const seeded=seedExecutionPrice(rows,buy,9320);
 assert.equal(seeded[0].price,9320);assert.equal(seeded[0].quantity,3);
 assert.equal(empty.price,0);
 assert.equal(seeded[1],edited);assert.equal(seeded[2],imported);assert.equal(seeded[3],unrelated);
 assert.equal(seedExecutionPrice(rows,buy,9320,{pending:true}),rows);
 assert.equal(seedExecutionPrice(rows,buy,0),rows);
});
