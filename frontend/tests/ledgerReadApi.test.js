import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
const originalFetch=globalThis.fetch;
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,configFile:false,logLevel:'error',cacheDir:'node_modules/.vite-test-ledger-api',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try {
 const {api,ledgerReadStore}=await server.ssrLoadModule('/src/utils/api.js');
 const auth=await server.ssrLoadModule('/src/utils/authSession.js');
 test('the real request path refreshes ledger readers once after trade/FX writes; quotes and performance capture do not refresh them',async()=>{
  let revision=1;const counts={usd:0,holdings:0,realized:0};
  auth.saveAuthSession({access_token:'synthetic-local-no-network',expires_at:Date.now()/1000+3600});
  globalThis.fetch=async(url,options)=>{
   const path=new URL(url).pathname;let body={ok:true};
   if(path==='/api/forex/'){counts.usd++;body={ledgers:[{usd_balance:100*revision}]};}
   else if(path==='/api/holdings/all'){counts.holdings++;body={holdings:[{quantity:5-revision}]};}
   else if(path==='/api/trades/realized'){counts.realized++;body={sales:[{gross_profit_krw:revision*1000}]};}
   else if(['POST','PUT','PATCH','DELETE'].includes(options.method) && !path.includes('/performance/'))revision++;
   return {ok:true,json:async()=>body};
  };
  const resources=['usd','holdings','realized'].map(kind=>ledgerReadStore.resource(kind,'p'));const stops=resources.map(r=>r.subscribe(()=>{}));
  await Promise.all(resources.map(r=>r.refresh()));assert.deepEqual(counts,{usd:1,holdings:1,realized:1});
  for(let i=0;i<10;i++)await api.getPortfolioBundle('p',false);
  await api.capturePerformance('p');await api.confirmPerformanceFlows('p',{});await Promise.all(resources.map(r=>r.refresh()));assert.deepEqual(counts,{usd:1,holdings:1,realized:1});
  await api.batchDeleteTrades(['synthetic-trade']);await Promise.all(resources.map(r=>r.refresh()));assert.deepEqual(counts,{usd:2,holdings:2,realized:2});
  await api.recordUsdEvent('a',{request_id:'synthetic-fx',portfolio_id:'p',usd_amount:1});await Promise.all(resources.map(r=>r.refresh()));assert.deepEqual(counts,{usd:3,holdings:3,realized:3});
  await api.getPortfolioBundle('p',true);await Promise.all(resources.map(r=>r.refresh()));assert.deepEqual(counts,{usd:4,holdings:4,realized:4});
  assert.equal(resources[1].getSnapshot().data.holdings[0].quantity,2);
  auth.clearAuthSession();resources.forEach(r=>assert.equal(r.getSnapshot().data,null));stops.forEach(stop=>stop());
 });
} finally {globalThis.fetch=originalFetch;await server.close();}
