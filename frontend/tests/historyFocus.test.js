import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {parseSync} from 'rolldown/experimental';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {recentMonths,recordAmount} from '../src/utils/activityHistory.js';
const noop=()=>{};
const modules=['HistoryTab','ActivityHistory','NamuhMessageImport','UsdLedgerPanel','TradeBatchForm'];
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),logLevel:'error',cacheDir:'node_modules/.vite-test-focus',server:{middlewareMode:true,watch:null,hmr:false,ws:false},
plugins:[{name:'focus-controls-fixture',enforce:'pre',transform(source,id,options){
 const name=path.basename(id,'.jsx');if(!options?.ssr || !modules.includes(name))return;
 const {program,errors}=parseSync(id,source);assert.equal(errors.length,0);const edits=[];
 function walk(node){if(!node || typeof node!=='object')return;
 if(node.type==='VariableDeclarator' && node.id.type==='ArrayPattern' && node.init?.callee?.name==='useState'){
 const key=node.id.elements[0]?.name,arg=node.init.arguments[0];if(arg)edits.push({start:arg.start,end:arg.end,text:`(Object.hasOwn(globalThis.__focusSeeds['${name}']||{},'${key}')?globalThis.__focusSeeds['${name}'].${key}:(${source.slice(arg.start,arg.end)}))`});}
 for(const v of Object.values(node))if(Array.isArray(v))v.forEach(walk);else if(v && typeof v==='object')walk(v);
 }walk(program);for(const e of edits.sort((a,b)=>b.start-a.start))source=source.slice(0,e.start)+e.text+source.slice(e.end);return source;
}}]});
const accounts=[{id:'a',account_no:'QA-001',account_alias:'QA',account_type:'GENERAL',portfolio_id:'p',deposit_usd:10,deposit_krw:4}];
const assets=[{id:'bond',name:'QA bond',ticker:'0085P0',market:'KR',portfolio_id:'p',allowed_accounts:['a']}];
const props={accounts,assets,currentPortfolioId:'p',priceMap:{},usdKrw:1400,onSaved:noop,onOpenAnalysis:noop,
 performance:{data:{tracking:{baseline_date:'2026-01-01'},flows:[]},busy:false,run:noop,capture:noop}};
const originals={storage:globalThis.localStorage,fetch:globalThis.fetch};globalThis.localStorage={getItem:()=>null,setItem:noop};globalThis.fetch=()=>{throw new Error('SSR must not perform record API writes');};
try{
 const History=(await server.ssrLoadModule('/src/components/Tab4History/HistoryTab.jsx')).default;
 const Records=(await server.ssrLoadModule('/src/components/Tab4History/ActivityHistory.jsx')).default;
 const render=(Component,props,seeds={})=>{globalThis.__focusSeeds=seeds;return renderToStaticMarkup(React.createElement(Component,props));};
 test('input is the default and history is hidden, with one selected NH method',()=>{
  const html=render(History,props);assert.match(html,/id="history-input-panel"[^>]*role="tabpanel"/);assert.match(html,/id="history-record-panel"[^>]*hidden=""/);
  assert.match(html,/aria-pressed="true"[^>]*>[^<]*<svg[\s\S]*?NH 알림 가져오기/);assert.match(html,/NH 알림 붙여넣기/);
  assert.doesNotMatch(html,/알림 반영 이력·묶음 취소|입출금 기록 확인|최근 매매 기록|가장 최근 기록 취소/);
 });
 test('switching views hides rather than unmounts manual entries and notifications',()=>{
  const html=render(History,props,{HistoryTab:{view:'records',method:'manual',buyRows:[{id:'draft',accountId:'a',assetId:'bond',quantity:17,price:9320,exchangeRate:1}]},NamuhMessageImport:{text:'붙여넣는 중인 초안'}});
  assert.match(html,/id="history-input-panel"[^>]*hidden=""/);assert.doesNotMatch(html,/id="history-record-panel"[^>]*hidden=""/);
  assert.match(html,/value="17"/);assert.match(html,/붙여넣는 중인 초안/);
 });
 test('focused dollar input shows current average but excludes the accumulated event table',()=>{
  const html=render(History,props,{HistoryTab:{method:'usd',usdLedgers:[{account_id:'a',average_rate:1300,usd_balance:10,cost_krw:13000,actual_usd:10}]}});
  assert.match(html,/평균 취득환율/);assert.match(html,/1,300\.0000/);assert.doesNotMatch(html,/처리 후 달러·평균환율|가장 최근 기록 취소/);
 });
 test('saving blocks changing work modes, while current form remains mounted',()=>{
  const html=render(History,props,{HistoryTab:{childBusy:{nh:true}}});assert.match(html,/id="history-record-tab"[^>]*disabled=""/);
  assert.match(html,/aria-pressed="false"[^>]*disabled=""/);assert.match(html,/NH 알림 붙여넣기/);
 });
 test('paged history keeps transaction details and batch cancel collapsed',()=>{
  const item={id:'FLOW:1',event_date:'2026-10-08',kind:'DEPOSIT',category:'CASH',account_alias:'QA',currency:'KRW',amount:960000,description:'외부 투자자금',batch_id:'batch-0001',detail:{flow_id:'1',cash_linked:true,cash_applied:true,amount_krw:960000}};
  const html=render(Records,{portfolioId:'p',accounts,active:true,onChanged:noop},{ActivityHistory:{data:{items:[item],page:1,pages:2,total:29},loading:false}});
  assert.match(html,/<details class="history-record-detail"><summary>/);assert.match(html,/이 알림 묶음 취소/);assert.match(html,/29건/);
  assert.match(html,/1 \/ 2 페이지/);assert.doesNotMatch(html,/<button[^>]*disabled=""[^>]*>다음/);
 });
 test('independent trades preserve symbol filtering and current-page bulk cancellation in details',()=>{
  const item={id:'TRADE:t',event_date:'2026-10-08',kind:'BUY',category:'TRADE',account_alias:'QA',currency:'KRW',amount:9320,description:'QA bond',detail:{trade_id:'t',asset_id:'bond',quantity:1,price:9320}};
  const html=render(Records,{portfolioId:'p',accounts,assets,active:true,onChanged:noop},{ActivityHistory:{filters:{start_date:'2026-10-01',end_date:'2026-10-08',category:'TRADE',account_id:'',asset_id:'bond'},selectedTrades:['t'],data:{items:[item],page:1,pages:1,total:1}}});
  assert.match(html,/기록 조회 종목/);assert.match(html,/선택한 매매 함께 취소/);assert.match(html,/여러 매매를 함께 취소할 목록에 선택/);assert.doesNotMatch(html,/이 알림 묶음 취소/);
 });
 test('default three-month period clamps month ends rather than overflowing',()=>{
  assert.equal(recentMonths('2026-05-31'),'2026-02-28');assert.equal(recentMonths('2024-05-31'),'2024-02-29');assert.equal(recentMonths('2026-01-15'),'2025-10-15');
 });
 test('FX labels preserve both currencies instead of looking like additional contributions',()=>{
  assert.equal(recordAmount({kind:'EXCHANGE_IN',currency:'USD',amount:717.31,detail:{krw_amount:959997}}),'959,997 원 → $717.31');
 });
}finally{globalThis.localStorage=originals.storage;globalThis.fetch=originals.fetch;delete globalThis.__focusSeeds;await server.close();}
