import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,logLevel:'error',cacheDir:'node_modules/.vite-test-execution',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
const originalFetch=globalThis.fetch;
globalThis.fetch=()=>{throw new Error('Execution screen must not call APIs');};
try {
 const View=(await server.ssrLoadModule('/src/components/Tab8Execution/ExecutionTab.jsx')).default;
 const step={id:'buy',kind:'BUY',title:'VT 매수',account_id:'us',account_alias:'직투 계좌',asset_id:'vt',asset_name:'VT',currency:'USD',target_quantity:5,depends_on:[]};
 const cycle={name:'QA 투자',portfolio_name:'QA',status:'ACTIVE',budget_krw:1000000,steps:[step],results:[]};
 const render=props=>renderToStaticMarkup(React.createElement(View,props));
 test('first view exposes the current task and keeps remaining and completed lists collapsed',()=>{
  const html=render({cycle,onRecord:()=>{}});
  assert.match(html,/aria-label="지금 할 일"/);assert.match(html,/체결 결과 입력/);
  assert.match(html,/<details class="section-card execution-list"><summary>남은 작업/);
  assert.doesNotMatch(html,/<details[^>]*open/);assert.match(html,/남은 작업 1건/);
 });
 test('unbooked execution cannot be shown as completion',()=>{
  const html=render({cycle:{...cycle,results:[{id:'fact',step_id:'buy',kind:'BUY',account_id:'us',asset_id:'vt',currency:'USD',quantity:5,ledger_status:'PENDING'}]},onRecord:()=>{}});
  assert.match(html,/기록을 먼저 확인해주세요/);assert.doesNotMatch(html,/체결 결과 입력/);
  assert.match(html,/작업 0 \/ 1 완료/);
 });
 test('empty and fully recorded screens remain useful without causing side effects',()=>{
  assert.match(render({}),/리밸런싱 계획 보기/);
  const html=render({cycle:{...cycle,results:[{id:'fill',step_id:'buy',kind:'BUY',account_id:'us',asset_id:'vt',currency:'USD',quantity:5,ledger_status:'RECORDED'}]},onCloseCycle:()=>{}});
  assert.match(html,/이번 투자 종료/);assert.match(html,/작업 1 \/ 1 완료/);
 });
} finally {globalThis.fetch=originalFetch;await server.close();}
