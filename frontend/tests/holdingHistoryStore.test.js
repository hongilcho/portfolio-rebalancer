import test from 'node:test';
import assert from 'node:assert/strict';
import {createHoldingHistoryStore, affectsHoldingHistory} from '../src/utils/holdingHistoryStore.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const history=value=>({rows:[{date:'2026-10-30',profit_krw:value}]});
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('concurrent mounts and StrictMode replay share one read; fresh tab revisits reuse it',async()=>{
 let calls=0;const gate=deferred();const store=createHoldingHistoryStore(()=>{calls++;return gate.promise;});
 const a=store.resource('p',false),b=store.resource('p',false);
 assert.equal(a,b);
 const first=a.refresh(),second=b.refresh();assert.equal(first,second);
 await tick();assert.equal(calls,1);
 gate.resolve(history(10));await first;await b.refresh();assert.equal(calls,1);
 assert.equal(a.getSnapshot().data.rows[0].profit_krw,10);
});
test('a slow refresh retains the graph and a failed refresh retains its last good records',async()=>{
 let result=history(10);const store=createHoldingHistoryStore(()=>result);
 const r=store.resource('p');await r.refresh();const before=r.getSnapshot().data;
 const gate=deferred();result=gate.promise;const job=r.refresh({force:true});
 assert.equal(r.getSnapshot().data,before);assert.equal(r.getSnapshot().loading,true);
 gate.reject(new Error('synthetic offline'));await job;
 assert.equal(r.getSnapshot().data,before);assert.equal(r.getSnapshot().loading,false);
 assert.match(r.getSnapshot().error,/이전 기록/);
 result=history(20);await r.refresh();assert.equal(r.getSnapshot().data.rows[0].profit_krw,20);
 assert.equal(r.getSnapshot().error,'');
});
test('portfolio and crypto inclusion switches cannot display a late response for a different scope',async()=>{
 const gates=new Map();const store=createHoldingHistoryStore((s,c)=>{const gate=deferred();gates.set(JSON.stringify([s,c]),gate);return gate.promise;});
 const a=store.resource('all',true),b=store.resource('all',false),c=store.resource('p',false);
 const jobs=[a.refresh(),b.refresh(),c.refresh()];await tick();
 gates.get('["all",false]').resolve(history(2));gates.get('["p",false]').resolve(history(3));await tick();
 assert.equal(a.getSnapshot().data,null);assert.equal(b.getSnapshot().data.rows[0].profit_krw,2);
 gates.get('["all",true]').resolve(history(1));await Promise.all(jobs);
 assert.equal(a.getSnapshot().data.rows[0].profit_krw,1);assert.equal(c.getSnapshot().data.rows[0].profit_krw,3);
});
test('time expiry detects new closes; current quote changes have no invalidation effect',async()=>{
 let clock=0,calls=0;const store=createHoldingHistoryStore(()=>history(++calls),{now:()=>clock,maxAge:60_000});
 const r=store.resource('p');await r.refresh();
 for(let i=0;i<10;i++){clock+=2000;await r.refresh();}
 assert.equal(calls,1);clock=60_000;await r.refresh();assert.equal(calls,2);
});
test('ledger changes refresh active views and mark unmounted aggregate/crypto histories stale',async()=>{
 let revision=1;const calls=[];const store=createHoldingHistoryStore((s,c)=>{calls.push([s,c]);return history(revision);});
 const p=store.resource('p'),all=store.resource('all',true),crypto=store.resource('crypto',true);
 await Promise.all([p.refresh(),all.refresh(),crypto.refresh()]);
 const unsub=p.subscribe(()=>{});revision=2;store.invalidate();await tick();
 assert.equal(p.getSnapshot().data.rows[0].profit_krw,2);assert.equal(calls.length,4);
 await Promise.all([all.refresh(),crypto.refresh()]);assert.equal(calls.length,6);
 assert.equal(all.getSnapshot().data.rows[0].profit_krw,2);unsub();
});
test('a write during an old read discards its response and coalesces writes into one follow-up',async()=>{
 const gates=[];const store=createHoldingHistoryStore(()=>{const gate=deferred();gates.push(gate);return gate.promise;});
 const r=store.resource('p');const unsub=r.subscribe(()=>{});
 const old=r.refresh();await tick();store.invalidate();store.invalidate();store.invalidate();
 gates[0].resolve(history(1));await old;await tick();
 assert.equal(r.getSnapshot().data,null);assert.equal(r.getSnapshot().loading,true);assert.equal(gates.length,2);
 gates[1].resolve(history(4));await tick();assert.equal(r.getSnapshot().data.rows[0].profit_krw,4);unsub();
});
test('unmount during an invalidated read queues no hidden request; next mount reads fresh data',async()=>{
 let calls=0;const gate=deferred();const store=createHoldingHistoryStore(()=>++calls===1?gate.promise:history(2));
 const r=store.resource('p'),unsub=r.subscribe(()=>{});const old=r.refresh();await tick();store.invalidate();unsub();
 gate.resolve(history(1));await old;assert.equal(calls,1);assert.equal(r.getSnapshot().data,null);
 await r.refresh();assert.equal(calls,2);assert.equal(r.getSnapshot().data.rows[0].profit_krw,2);
});
test('logout drops cached financial data and late responses cannot repopulate it or overwrite a new login',async()=>{
 let calls=0;const gate=deferred();const store=createHoldingHistoryStore(()=>++calls===1?gate.promise:history(2));
 const r=store.resource('p');const old=r.refresh();await tick();store.clear();
 assert.equal(r.getSnapshot().data,null);await r.refresh();gate.resolve(history(1));await old;
 assert.equal(r.getSnapshot().data.rows[0].profit_krw,2);assert.equal(r.getSnapshot().loading,false);
 store.clear();assert.equal(r.getSnapshot().data,null);
});
test('only relevant writes and explicit refreshes invalidate history, never ordinary price polling or previews',()=>{
 for(const path of ['/api/trades/batch','/api/nh-notices/p/batch','/api/forex/a/events','/api/ledger-adjustments/p','/api/crypto/holdings','/api/performance/p/snapshot','/api/rebalance/apply-transfers','/api/sync/namuh'])assert.equal(affectsHoldingHistory(path,'POST'),true,path);
 assert.equal(affectsHoldingHistory('/api/trades/batch','DELETE'),true);
 assert.equal(affectsHoldingHistory('/api/accounts/a','PATCH'),true);
 for(const path of ['/api/dashboard/bundle?force_refresh=false','/api/performance/holding-history?scope=all','/api/crypto/summary'])assert.equal(affectsHoldingHistory(path),false,path);
 for(const path of ['/api/auth/verify','/api/rebalance/calculate','/api/ledger-adjustments/p/preview','/api/ledger-adjustments/p/settlement-preview','/api/cma/p/a/observe','/api/investments/p'])assert.equal(affectsHoldingHistory(path,'POST'),false,path);
 assert.equal(affectsHoldingHistory('/api/dashboard/bundle?force_refresh=true'),true);
});
