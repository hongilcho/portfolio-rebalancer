import test from 'node:test';
import assert from 'node:assert/strict';
import {draftStorage,readTradeDraft,writeTradeDraft} from '../src/utils/tradeDraft.js';
import {readNoticeDraft,writeNoticeDraft} from '../src/utils/nhNotices.js';
import {pendingInvestmentSteps} from '../src/utils/investmentDrafts.js';
import {readPendingRequest,persistPendingRequest} from '../src/utils/bookkeepingRequest.js';

test('5 and 8 keep separate drafts and exact retry requests while using the same portfolio ID',()=>{
 const previous=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
 const values=new Map(),store={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 Object.defineProperty(globalThis,'localStorage',{configurable:true,value:store});
 try {
  const normal=draftStorage(),task=draftStorage('execution/cycle/task'),other=draftStorage('execution/cycle/other');
  const row={id:'row',accountId:'isa',assetId:'bond',quantity:2,price:9000,exchangeRate:1};
  const draft={tradeDate:'2026-10-10',buyRows:[row],sellRows:[]};
  assert.equal(writeTradeDraft(normal,'default',draft),true);
  assert.equal(readTradeDraft(task,'default'),null);
  const pending={request_id:'stable-request',portfolio_id:'default',trades:[{quantity:3,execution:{cycle_id:'cycle',step_id:'task',revision:1}}]};
  assert.equal(writeTradeDraft(task,'default',{...draft,buyRows:[{...row,quantity:3}],pendingSubmission:pending}),true);
  assert.equal(readTradeDraft(normal,'default').buyRows[0].quantity,2);
  assert.deepEqual(readTradeDraft(draftStorage('execution/cycle/task'),'default').pendingSubmission,pending);
  assert.equal(readTradeDraft(other,'default'),null);
  const notice={id:'notice',kind:'BUY',eventDate:'2026-10-10',accountId:'isa',errors:[]};
  assert.equal(writeNoticeDraft('default',{rows:[notice]},task),true);
  assert.equal(readNoticeDraft('default',normal),null);
  assert.equal(readNoticeDraft('default',task).rows[0].id,'notice');
  const request={payload:{request_id:'exact-forex-request',execution:{cycle_id:'cycle',step_id:'task',revision:1}}};
  persistPendingRequest('manual-forex/v1/default',request,task);
  assert.equal(readPendingRequest('manual-forex/v1/default',normal),null);
  assert.deepEqual(readPendingRequest('manual-forex/v1/default',task),request);
  assert.deepEqual(pendingInvestmentSteps({id:'cycle',status:'CLOSED',steps:[{id:'task'},{id:'other'}]},'default'),[{id:'task'}]);
  writeNoticeDraft('default',{rows:[]},task);
  assert.equal(readTradeDraft(normal,'default').buyRows[0].quantity,2);
 } finally {if(previous)Object.defineProperty(globalThis,'localStorage',previous);else delete globalThis.localStorage;}
});
