import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
import {feePayload,remainingSellQuantity} from '../src/utils/tradeCosts.js';
import {readTradeDraft,writeTradeDraft} from '../src/utils/tradeDraft.js';

test('unknown costs stay omitted; explicit zero and USD/KRW actual fees are distinct',()=>{
  assert.deepEqual(feePayload({feesKrw:10},false),{});
  assert.deepEqual(feePayload({costsConfirmed:true},false),{fees_krw:0,fees_usd:0});
  assert.deepEqual(feePayload({costsConfirmed:true,feesKrw:20,feesUsd:1},true),{fees_krw:20,fees_usd:1});
  for(const bad of [-1,NaN,Infinity,1e13])assert.throws(()=>feePayload({costsConfirmed:true,feesKrw:bad},false));
});
test('full sale subtracts only other drafts for the same account and security',()=>{
  const r={id:'a',accountId:'one',assetId:'vt',quantity:1};
  const rows=[r,{id:'b',accountId:'one',assetId:'vt',quantity:3},{id:'c',accountId:'two',assetId:'vt',quantity:100}];
  assert.equal(remainingSellQuantity(r,rows,[{asset_id:'vt',quantity:10}]),7);
  assert.equal(remainingSellQuantity(r,rows,[{asset_id:'vt',quantity:2}]),0);
});
test('restored local drafts retain explicitly confirmed fees',()=>{
  const store=new Map(),storage={setItem:(k,v)=>store.set(k,v),getItem:k=>store.get(k),removeItem:k=>store.delete(k)};
  const row={id:'r',accountId:'one',assetId:'vt',quantity:2,price:100,exchangeRate:1300,costsConfirmed:true,feesUsd:1,feesKrw:20};
  writeTradeDraft(storage,'p',{tradeDate:'2026-10-16',buyRows:[],sellRows:[row]});
  assert.deepEqual(readTradeDraft(storage,'p').sellRows,[row]);
});

const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,logLevel:'error',
  cacheDir:'node_modules/.vite-test-realized',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try{
  const Panel=(await server.ssrLoadModule('/src/components/Tab6Analysis/RealizedGainsPanel.jsx')).default;
  const Costs=(await server.ssrLoadModule('/src/components/Tab4History/TradeCosts.jsx')).default;
  test('report exposes sale and full liquidation history without turning missing basis into zero',()=>{
    const html=renderToStaticMarkup(React.createElement(Panel,{portfolioId:'p',initialData:{
      summary:{gross_profit_krw:null,confirmed_net_profit_krw:null,pending_count:1},periods:[],warnings:[],
      sales:[{trade_id:'s',asset_name:'합성 VT',account_alias:'QA',trade_date:'2026-10-16',quantity:1,status:'BASIS_PENDING',currency:'USD'}]}}));
    assert.match(html,/전량 매도 완료/);assert.match(html,/매도별 손익/);assert.match(html,/원가 확인 필요/);
    assert.match(html,/확인 필요/);assert.match(html,/실현손익과 매도 이력/);
    assert.doesNotMatch(html,/0 원/);assert.doesNotMatch(html,/min-width:.*600px/);
  });
  test('fee disclosure is optional, closed by default, and distinguishes actual cash deductions',()=>{
    const html=renderToStaticMarkup(React.createElement(Costs,{row:{costsConfirmed:false},isUS:true,onChange:()=>{}}));
    assert.doesNotMatch(html,/<details[^>]*open/);assert.match(html,/거래는 저장/);
    const confirmed=renderToStaticMarkup(React.createElement(Costs,{row:{costsConfirmed:true,feesUsd:1},isUS:true,onChange:()=>{}}));
    assert.match(confirmed,/달러 비용 합계/);assert.match(confirmed,/예수금에서 함께 차감/);
  });
}finally{await server.close();}
