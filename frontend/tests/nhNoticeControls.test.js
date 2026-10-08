import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {parseSync} from 'rolldown/experimental';
import {fileURLToPath} from 'node:url';
import {parseNhNotifications,resolveNhNotice} from '../src/utils/nhNotices.js';

// Seed states in the same SSR transformation used for presentation regression.
// Rendering uses the real components and validators; no browser or API writes.
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),logLevel:'error',
  cacheDir:'node_modules/.vite-test-nh-controls',server:{middlewareMode:true,watch:null,hmr:false,ws:false},
  plugins:[{name:'nh-control-state',enforce:'pre',transform(source,id,options){
    if(!options?.ssr || !/(NamuhMessageImport|EditHoldingsModal)\.jsx$/.test(id))return;
    const {program,errors}=parseSync(id,source);assert.equal(errors.length,0);const edits=[];
    function walk(node){
      if(!node || typeof node!=='object')return;
      if(node.type==='VariableDeclarator' && node.id.type==='ArrayPattern' && node.init?.callee?.name==='useState'){
        const key=node.id.elements[0]?.name,arg=node.init.arguments[0];
        if(arg)edits.push({start:arg.start,end:arg.end,text:`(Object.hasOwn(globalThis.__nhStates,'${key}')?globalThis.__nhStates.${key}:(${source.slice(arg.start,arg.end)}))`});
      }
      for(const value of Object.values(node))if(Array.isArray(value))value.forEach(walk);else if(value && typeof value==='object')walk(value);
    }
    walk(program);for(const e of edits.sort((a,b)=>b.start-a.start))source=source.slice(0,e.start)+e.text+source.slice(e.end);
    return source;
  }}]});
const noop=()=>{};
const accounts=[{id:'isa',portfolio_id:'p',account_no:'123-45-671232',account_alias:'ISA',account_type:'ISA',deposit_krw:190000,deposit_usd:0},
  {id:'usd',portfolio_id:'p',account_no:'123-45-671231',account_alias:'USD',account_type:'GENERAL',deposit_krw:4,deposit_usd:10}];
const assets=[{id:'bond',portfolio_id:'p',name:'QA bond',ticker:'0085P0',market:'KR',allowed_accounts:['isa']}];
const day='2026-10-08';
const context={accounts,flows:[{id:'old',account_id:'usd',currency:'KRW',amount_krw:960000}],trades:[],notices:[],exchanges:[],batches:[]};
const ledgers=[{account_id:'usd',usd_balance:10,cost_krw:13000,last_event_date:'2026-10-05',needs_reconciliation:false}];
const props={accounts,assets,portfolioId:'p',tradeDate:day,buyRows:[],ledgers,onChanged:noop};
const buy='[NH투자증권] 매수 주문체결 알림\n종목명: QA bond\n종목코드: 0085P0\n체결종류: 매수 전량 체결\n체결수량: 1주\n체결단가: 9,320원\n주문번호: 42954';
const row={...resolveNhNotice(parseNhNotifications(buy,day)[0],accounts,assets,'p'),id:'qa-buy'};
const originalStorage=globalThis.localStorage;
globalThis.localStorage={getItem:()=>null,setItem:noop,removeItem:noop};
try{
  const Import=(await server.ssrLoadModule('/src/components/Tab4History/NamuhMessageImport.jsx')).default;
  const Edit=(await server.ssrLoadModule('/src/components/Tab1Dashboard/EditHoldingsModal.jsx')).default;
  const render=(component,props,state)=>{globalThis.__nhStates=state;return renderToStaticMarkup(React.createElement(component,props));};
  const state={open:true,rows:[row],contexts:{[day]:context},confirmed:true,loading:false};
  test('a missing-account buy cannot save until manual account choice, then final confirmation enables save',()=>{
    const missing=render(Import,props,state);assert.match(missing,/<button[^>]*disabled=""[^>]*>확인한 알림 1건 장부에 일괄 반영/);
    const corrected=render(Import,props,{...state,rows:[{...row,accountId:'isa'}]});
    assert.match(corrected,/<button type="button" class="btn btn-primary">확인한 알림 1건 장부에 일괄 반영/);
    assert.doesNotMatch(corrected,/role="alert"/);
    const unchecked=render(Import,props,{...state,rows:[{...row,accountId:'isa'}],confirmed:false});
    assert.match(unchecked,/<button[^>]*disabled=""[^>]*>확인한 알림 1건 장부에 일괄 반영/);
  });
  test('deposit and exchange remain a single review with existing-flow link and seven-won preview',()=>{
    const deposit={id:'qa-deposit',kind:'DEPOSIT',accountId:'usd',eventDate:day,krwAmount:960000,external:true,applyCash:true,errors:[],fingerprint:'a'.repeat(64)};
    const exchange={id:'qa-exchange',kind:'EXCHANGE_IN',accountId:'usd',eventDate:day,krwAmount:959997,usdAmount:717.31,quotedRate:1338.33,external:true,errors:[],fingerprint:'b'.repeat(64)};
    const html=render(Import,props,{...state,rows:[deposit,exchange]});
    assert.match(html,/<option value="old" selected="">기존 960,000 원 입금에 연결/);
    assert.match(html,/USD · 원화 7 원 · 달러 \$727\.31/);
    assert.match(html,/<button type="button" class="btn btn-primary">확인한 알림 2건 장부에 일괄 반영/);
  });
  test('withdrawal controls show available balance only as a reference and old history preserves cash',()=>{
    const old={id:'qa-old-withdrawal',kind:'WITHDRAW',accountId:'usd',eventDate:'2026-09-30',krwAmount:1000000,reportedAvailableKrw:38239177,external:true,applyCash:false,errors:[],fingerprint:'d'.repeat(64)};
    const ctx={...context,flows:[],trackings:{p:{baseline_date:'2026-10-05'}}};
    const html=render(Import,props,{...state,rows:[old],contexts:{'2026-09-30':ctx}});
    assert.match(html,/원화 출금/);assert.match(html,/출금가능금액 38,239,177 원/);
    assert.match(html,/잔고를 덮어쓰지 않습니다/);assert.match(html,/성과 기준일 이전 기록/);
    assert.match(html,/<button type="button" class="btn btn-primary">확인한 알림 1건 장부에 일괄 반영/);
  });
  test('cross portfolio transfer has a counterparty choice and previews both accounts before saving',()=>{
    const transfer={id:'qa-transfer',kind:'WITHDRAW',accountId:'usd',destinationAccountId:'peer',eventDate:day,krwAmount:3,external:false,crossPortfolio:true,applyCash:true,errors:[],fingerprint:'e'.repeat(64)};
    const ctx={...context,flows:[],transfer_accounts:[{id:'peer',portfolio_id:'pool',portfolio_name:'Liquidity',account_alias:'CMA pool',deposit_krw:100,deposit_usd:0}]};
    const html=render(Import,props,{...state,rows:[transfer],contexts:{[day]:ctx}});
    assert.match(html,/<option value="CROSS" selected="">포트폴리오 간 이체/);assert.match(html,/Liquidity · CMA pool/);
    assert.match(html,/CMA pool · 원화 103 원/);assert.match(html,/USD · 원화 1 원/);
    assert.match(html,/<button type="button" class="btn btn-primary">확인한 알림 1건 장부에 일괄 반영/);
  });
  test('an uncertain saved request freezes draft editing while offering identical-result retry',()=>{
    const html=render(Import,props,{...state,pendingPayload:{request_id:'QA-retry'}});
    assert.match(html,/<fieldset disabled=""/);assert.match(html,/동일 요청의 저장 결과 다시 확인/);
  });
  test('tracked USD account permits KRW-only save, while USD and holding inputs remain locked',()=>{
    const html=render(Edit,{accounts,assets,onSaved:noop,onClose:noop},{selectedAccId:'usd',depositKrw:960004,depositUsd:10,
      ledgerStatus:{accountId:'usd',ready:true,tracked:true,error:''}});
    assert.match(html,/<input[^>]*disabled=""[^>]*value="10"/);
    assert.match(html,/<fieldset disabled=""/);
    assert.match(html,/<button[^>]*class="btn btn-primary btn-block"[^>]*>💾 원화 예수금만 저장/);
    assert.doesNotMatch(html,/<button[^>]*disabled=""[^>]*>💾 원화 예수금만 저장/);
  });
  test('unknown USD tracking state blocks save during account switch',()=>{
    const html=render(Edit,{accounts,assets,onSaved:noop,onClose:noop},{selectedAccId:'usd',ledgerStatus:{accountId:'isa',ready:true,tracked:false,error:''}});
    assert.match(html,/<button[^>]*disabled=""[^>]*>💾 예수금 및 보유 수량\/평단가 저장/);
  });
}finally{globalThis.localStorage=originalStorage;delete globalThis.__nhStates;await server.close();}
