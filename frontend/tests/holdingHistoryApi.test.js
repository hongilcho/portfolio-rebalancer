import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
const originalFetch=globalThis.fetch;
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,configFile:false,logLevel:'error',cacheDir:'node_modules/.vite-test-history-api',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try {
 const {api,holdingHistoryStore}=await server.ssrLoadModule('/src/utils/api.js');
 const auth=await server.ssrLoadModule('/src/utils/authSession.js');
 test('the real API client invalidates history after a ledger write and explicit refresh, but not price reads or calculations',async()=>{
  let reads=0,revision=1;const calls=[];
  auth.saveAuthSession({access_token:'synthetic-local-only',expires_at:Date.now()/1000+3600});
  globalThis.fetch=async(url,options)=>{
   calls.push([url,options.method||'GET']);
   if(url.includes('/holding-history?')){reads++;return {ok:true,json:async()=>({rows:[{profit_krw:revision}]})};}
   if(options.method==='DELETE')revision++;
   return {ok:true,json:async()=>({ok:true})};
  };
  const resource=holdingHistoryStore.resource('p',false),unsubscribe=resource.subscribe(()=>{});
  await resource.refresh();assert.equal(reads,1);
  await api.getPortfolioBundle('p',false);await api.calculateRebalance({});await resource.refresh();assert.equal(reads,1);
  await api.batchDeleteTrades(['synthetic-trade']);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(reads,2);assert.equal(resource.getSnapshot().data.rows[0].profit_krw,2);
  await api.getPortfolioBundle('p',true);await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,3);
  assert.ok(calls.every(([url])=>url.startsWith('http://localhost:8000/'))); // Every request intercepted above.
  auth.clearAuthSession();assert.equal(resource.getSnapshot().data,null);unsubscribe();
 });
} finally {globalThis.fetch=originalFetch;await server.close();}
