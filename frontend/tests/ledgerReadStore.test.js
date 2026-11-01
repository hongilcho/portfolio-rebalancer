import test from 'node:test';
import assert from 'node:assert/strict';
import {createLedgerReadStore,normalizedReadFilters} from '../src/utils/ledgerReadStore.js';
import {groupAccountHoldings} from '../src/utils/accountHoldings.js';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const clientFor=(fn)=>({getUsdLedgers:p=>fn('usd',p),getAllHoldings:p=>fn('holdings',p),getRealizedGains:(p,f)=>fn('realized',p,f)});

test('tab 5 and tab 8 subscribers share one dollar and holdings query while quotes and array identities change',async()=>{
 const calls=[];const client=clientFor((kind,p)=>{calls.push([kind,p]);return kind==='usd'?{ledgers:[{account_id:'a',usd_balance:10.25,average_rate:1338.33}]}:{holdings:[{account_id:'a',asset_id:'vt',quantity:3.5}]};});
 const store=createLedgerReadStore(client);const usd=store.resource('usd','p'),holdings=store.resource('holdings','p');
 const stop=[usd.subscribe(()=>{}),usd.subscribe(()=>{}),holdings.subscribe(()=>{}),holdings.subscribe(()=>{})];
 await Promise.all([usd.refresh(),usd.refresh(),holdings.refresh(),holdings.refresh()]);
 for(let i=0;i<30;i++){
  const accounts=[{id:'a',deposit_usd:10.25,price:i}];
  assert.equal(groupAccountHoldings(accounts,holdings.getSnapshot().data.holdings).a[0].quantity,3.5);
  await Promise.all([store.resource('usd','p').refresh(),store.resource('holdings','p').refresh()]);
 }
 assert.deepEqual(calls,[['usd','p'],['holdings','p']]);stop.forEach(fn=>fn());
});
test('realized filters have stable sorted keys and cannot mix portfolios or late filtered responses',async()=>{
 const gates=[];const store=createLedgerReadStore(clientFor((kind,p,filters)=>{const gate=deferred();gates.push({gate,kind,p,filters});return gate.promise;}));
 const a=store.resource('realized','p',{account_id:'a',start_date:'2026-10-01',end_date:''});
 assert.equal(a,store.resource('realized','p',{start_date:'2026-10-01',account_id:'a'}));
 const b=store.resource('realized','q',{account_id:'a'}),c=store.resource('realized','p',{account_id:'b'});
 const jobs=[a.refresh(),b.refresh(),c.refresh()];await tick();
 gates[2].gate.resolve({sales:[{trade_id:'new-filter'}]});await jobs[2];assert.equal(c.getSnapshot().data.sales[0].trade_id,'new-filter');assert.equal(a.getSnapshot().data,null);
 gates[0].gate.resolve({sales:[{trade_id:'old-filter'}]});gates[1].gate.resolve({sales:[{trade_id:'other-portfolio'}]});await Promise.all(jobs);
 assert.equal(c.getSnapshot().data.sales[0].trade_id,'new-filter');assert.equal(b.getSnapshot().data.sales[0].trade_id,'other-portfolio');
 assert.deepEqual(normalizedReadFilters({asset_id:null,account_id:'a',end_date:''}),{account_id:'a'});
});
test('write invalidation immediately marks cached quantities stale, retains display and updates all active kinds once',async()=>{
 let qty=5;const counts={};const store=createLedgerReadStore(clientFor(kind=>{counts[kind]=(counts[kind]||0)+1;return kind==='holdings'?{holdings:[{account_id:'a',quantity:qty}]}:{version:qty};}));
 const resources=['usd','holdings','realized'].map(kind=>store.resource(kind,'p'));const stop=resources.map(r=>r.subscribe(()=>{}));
 await Promise.all(resources.map(r=>r.refresh()));qty=3;store.invalidate();
 assert.equal(resources[1].getSnapshot().data.holdings[0].quantity,5);assert.equal(resources[1].getSnapshot().stale,true);
 await Promise.all(resources.map(r=>r.refresh()));assert.equal(resources[1].getSnapshot().data.holdings[0].quantity,3);assert.equal(resources[1].getSnapshot().stale,false);
 assert.deepEqual(counts,{usd:2,holdings:2,realized:2});stop.forEach(fn=>fn());
});
test('a write racing an initial read never makes its old quantity usable; waiters finish after the post-write read',async()=>{
 const gates=[];const store=createLedgerReadStore(clientFor(()=>{const gate=deferred();gates.push(gate);return gate.promise;}));const r=store.resource('holdings','p'),stop=r.subscribe(()=>{});
 let settled=false;const waiter=r.refresh().then(value=>{settled=true;return value;});await tick();store.invalidate();store.invalidate();
 gates[0].resolve({holdings:[{quantity:5}]});await tick();assert.equal(settled,false);assert.equal(r.getSnapshot().data,null);assert.equal(gates.length,2);
 gates[1].resolve({holdings:[{quantity:3}]});assert.equal((await waiter).holdings[0].quantity,3);assert.equal(r.getSnapshot().stale,false);stop();
});
test('failed balance refresh keeps old data explicitly stale and retry recovers without any write',async()=>{
 let fail=false;const store=createLedgerReadStore(clientFor(()=>{if(fail)throw Error('synthetic offline');return {holdings:[{quantity:3}]};}));const r=store.resource('holdings','p');await r.refresh();
 fail=true;assert.equal(await r.refresh({force:true}),null);assert.equal(r.getSnapshot().data.holdings[0].quantity,3);assert.equal(r.getSnapshot().stale,true);assert.match(r.getSnapshot().error,/offline/);
 fail=false;await r.refresh();assert.equal(r.getSnapshot().stale,false);assert.equal(r.getSnapshot().error,'');
});
test('inactive tabs queue no invalidation reads and reactivation refreshes; expiry checks remain bounded',async()=>{
 let calls=0,clock=0;const store=createLedgerReadStore(clientFor(()=>({version:++calls})),{now:()=>clock,maxAge:60_000});const r=store.resource('usd','p');
 await r.refresh();store.invalidate();assert.equal(calls,1);await r.refresh();assert.equal(calls,2);
 clock=59_999;await r.refresh();assert.equal(calls,2);clock=60_000;await r.refresh();assert.equal(calls,3);
});
test('logout clears all financial read caches and late responses cannot restore old data after re-login',async()=>{
 const gate=deferred();let calls=0;const store=createLedgerReadStore(clientFor(()=>++calls===1?gate.promise:{ledgers:[{usd_balance:2}]}));const r=store.resource('usd','p');
 const old=r.refresh();await tick();store.clear();assert.equal(r.getSnapshot().data,null);await r.refresh();gate.resolve({ledgers:[{usd_balance:999}]});await old;
 assert.equal(r.getSnapshot().data.ledgers[0].usd_balance,2);store.clear();assert.equal(r.getSnapshot().data,null);
});
