import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,configFile:false,logLevel:'error',cacheDir:'node_modules/.vite-test-ledger-controls',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try {
 const Form=(await server.ssrLoadModule('/src/components/Tab4History/TradeBatchForm.jsx')).default;
 test('cached sell quantity remains visible but full-sale autofill waits for a fresh successful balance; typed fields remain editable',()=>{
  const props={tradeDate:'2026-10-30',buyRows:[],sellRows:[{id:'s',accountId:'a',assetId:'vt',quantity:2,price:101.5,exchangeRate:1338.33}],assets:[{id:'vt',name:'VT',market:'US',allowed_accounts:['a']}],accounts:[{id:'a',account_alias:'QA'}],accountHoldingsMap:{a:[{account_id:'a',asset_id:'vt',quantity:5}]},usdKrw:1338.33};
  const render=extra=>renderToStaticMarkup(React.createElement(Form,{...props,...extra}));
  const stale=render({balancesPending:true});assert.match(stale,/<button[^>]*disabled=""[^>]*>전량 5주<\/button>/);assert.match(stale,/value="2"/);assert.match(stale,/value="101.5"/);
  const fresh=render({balancesPending:false});assert.doesNotMatch(fresh,/<button[^>]*disabled=""[^>]*>전량 5주<\/button>/);
  const failed=render({holdingsError:true});assert.match(failed,/<button[^>]*disabled=""[^>]*>전량 5주<\/button>/);
 });
} finally {await server.close();}
