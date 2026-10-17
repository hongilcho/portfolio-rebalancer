import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {accountWithoutDeposits} from '../src/utils/accountPresentation.js';

const account={id:'cma',account_no:'QA',account_alias:'QA CMA',account_type:'CMA',
  deposit_krw:1040,deposit_usd:0,stock_eval:0,stock_buy_total:0,total_val:1040,
  profit_krw:40,profit_pct:0,cma_interest_krw:40,holdings:[]};
test('deposit filter keeps paid CMA income, cash and total; stock return excludes cash interest',()=>{
  const input={...account,holdings:[
    {eval_amount:110,buy_amount:100,quantity:1,avg_price:100,dividend_profit_krw:5},
    {is_deposit:true,eval_amount:205,buy_amount:200,quantity:1,avg_price:200}]};
  const snapshot=structuredClone(input),filtered=accountWithoutDeposits(input,1400);
  assert.equal(filtered.profit_krw,55);assert.equal(filtered.profit_pct,15);
  assert.equal(filtered.total_val,1150);assert.equal(filtered.deposit_krw,1040);
  assert.equal(filtered.cma_interest_krw,40);assert.deepEqual(input,snapshot);
});

const originalFetch=globalThis.fetch;
globalThis.fetch=()=>{throw Error('Account UI must not call external APIs');};
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,configFile:false,
  logLevel:'error',cacheDir:'node_modules/.vite-test-cma-account',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try{
  const Panel=(await server.ssrLoadModule('/src/components/Tab1Dashboard/AccountBreakdown.jsx')).default;
  const render=acc=>renderToStaticMarkup(React.createElement(Panel,{includeDeposits:true,displayAccSummaries:[acc],
    expandedAccs:{cma:true},usd_krw:1400,toggleAccordion:()=>{},currencyMode:'KRW'}));
  test('cash-only CMA shows income separately and in profit without doubling assets',()=>{
    const html=render(account);
    assert.match(html,/CMA 누적 세후 이자/);assert.match(html,/초기 누적분 포함 · 예수금에 이미 반영됨/);
    assert.match(html,/\+40 원/);assert.match(html,/보유자산 수익률 —/);
    assert.match(html,/1,040 원/);assert.doesNotMatch(html,/1,080 원|미지급/);
  });
  test('zero combined profit is preserved when held assets lose exactly the paid interest',()=>{
    const html=render({...account,stock_eval:60,stock_buy_total:100,profit_krw:0,profit_pct:-40});
    assert.match(html,/보유자산 수익률 -40.0%/);
    assert.doesNotMatch(html,/>-40 원</);
  });
  test('unrelated accounts keep existing profit labels and no CMA income panel',()=>{
    const html=render({...account,account_type:'GENERAL'});
    assert.match(html,/총손익 \(수익률\)/);assert.doesNotMatch(html,/CMA 누적 세후 이자/);
  });
}finally{await server.close();globalThis.fetch=originalFetch;}
