import test from 'node:test';
import assert from 'node:assert/strict';
import {startSummaryAndHistory,performanceViewActive} from '../src/utils/viewLoading.js';
import {createHoldingHistoryStore} from '../src/utils/holdingHistoryStore.js';
import {createPerformanceStore} from '../src/utils/performanceStore.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('history starts before summary resolves and graph mount joins the same request',async()=>{
 const summary=deferred(),history=deferred(),calls=[];
 const store=createHoldingHistoryStore((scope,crypto)=>{calls.push(['history',scope,crypto]);return history.promise;});
 const resource=store.resource('all',true);
 const result=startSummaryAndHistory(()=>{calls.push(['summary']);return summary.promise;},resource);
 await tick();assert.deepEqual(calls,[['summary'],['history','all',true]]);
 const stop=resource.subscribe(()=>{}),mounted=resource.refresh();assert.equal(calls.length,2);
 history.resolve({rows:[{profit_krw:123}]});await mounted;assert.equal(resource.getSnapshot().data.rows[0].profit_krw,123);
 summary.resolve({ready:true});assert.deepEqual(await result,{ready:true});await resource.refresh();assert.equal(calls.length,2);stop();
});

test('failed history does not block summary or replace the normal graph error',async()=>{
 const store=createHoldingHistoryStore(async()=>{throw new Error('synthetic failure');});const resource=store.resource('all',false);
 assert.deepEqual(await startSummaryAndHistory(async()=>({ready:true}),resource),{ready:true});
 await resource.refresh();assert.match(resource.getSnapshot().error,/과거 기록/);
});

test('failed summary does not cancel a successful graph read',async()=>{
 const store=createHoldingHistoryStore(async()=>({rows:[]}));const resource=store.resource('crypto',true);
 await assert.rejects(startSummaryAndHistory(async()=>{throw new Error('summary');},resource));
 await resource.refresh();assert.deepEqual(resource.getSnapshot().data,{rows:[]});
});

test('a write racing prefetch discards old data and graph mount waits for the new revision',async()=>{
 const gate=deferred();let reads=0;const store=createHoldingHistoryStore(()=>++reads===1?gate.promise:Promise.resolve({revision:2}));
 const resource=store.resource('all',true);await startSummaryAndHistory(async()=>({}),resource);await tick();
 store.invalidate();const stop=resource.subscribe(()=>{}),mounted=resource.refresh();gate.resolve({revision:1});await mounted;
 assert.equal(reads,2);assert.equal(resource.getSnapshot().data.revision,2);assert.equal(resource.getSnapshot().stale,false);stop();
});

test('crypto inclusion uses independent keys and a late old toggle cannot replace the selected result',async()=>{
 const gates=[deferred(),deferred()];let reads=0;const store=createHoldingHistoryStore(()=>gates[reads++].promise);
 const financial=store.resource('all',false),all=store.resource('all',true);
 await startSummaryAndHistory(async()=>({}),financial);await startSummaryAndHistory(async()=>({}),all);await tick();
 gates[1].resolve({include_crypto:true});await all.refresh();gates[0].resolve({include_crypto:false});await financial.refresh();
 assert.equal(reads,2);assert.equal(all.getSnapshot().data.include_crypto,true);assert.equal(financial.getSnapshot().data.include_crypto,false);
});

test('only bookkeeping, analysis and open investment inputs request period details',()=>{
 for(const tab of ['tab1','accounts','tab2','tab3','tab5'])assert.equal(performanceViewActive(tab,{step:'unused'}),false);
 assert.equal(performanceViewActive('tab4',null),true);assert.equal(performanceViewActive('tab6',null),true);
 assert.equal(performanceViewActive('tab8',null),false);assert.equal(performanceViewActive('tab8',{step:'input'}),true);
});

test('returning to a dormant view clears completed busy state and bookkeeping still refreshes period records',async()=>{
 const gate=deferred(),entered=deferred();let reads=0,writes=0;
 const store=createPerformanceStore('p',{getPerformance:async()=>{if(++reads===1){entered.resolve();return gate.promise;}return {revision:2};}});
 store.setEnabled(true);const pending=store.refresh();await entered.promise;store.setEnabled(false);gate.resolve({revision:1});await pending;
 store.setEnabled(true);assert.equal(store.getSnapshot().busy,false);assert.equal(store.getSnapshot().data,null);
 await store.run(async()=>{writes++;});assert.equal(writes,1);assert.equal(reads,2);assert.equal(store.getSnapshot().data.revision,2);
});
