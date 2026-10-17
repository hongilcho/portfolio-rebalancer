import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {parseSync} from 'rolldown/experimental';

const originalFetch=globalThis.fetch;
globalThis.fetch=()=>{throw Error('CMA UI tests must not call external APIs');};
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,logLevel:'error',
  cacheDir:'node_modules/.vite-test-cma',server:{middlewareMode:true,watch:null,hmr:false,ws:false},
  plugins:[{name:'cma-synthetic-state',enforce:'pre',transform(source,id,options){
    if(!options?.ssr || !id.endsWith('/CmaIncomePanel.jsx'))return;
    const {program,errors}=parseSync(id,source);assert.equal(errors.length,0);const edits=[];
    const walk=node=>{if(!node || typeof node!=='object')return;
      if(node.type==='VariableDeclarator' && node.id.type==='ArrayPattern' && node.init?.callee?.name==='useState'){
        const state=node.id.elements[0]?.name,arg=node.init.arguments[0];
        if(arg)edits.push({start:arg.start,end:arg.end,text:`(Object.hasOwn(globalThis.__cmaState,'${state}')?globalThis.__cmaState.${state}:(${source.slice(arg.start,arg.end)}))`});
      }
      for(const v of Object.values(node))if(Array.isArray(v))v.forEach(walk);else if(v && typeof v==='object')walk(v);
    };walk(program);for(const e of edits.sort((a,b)=>b.start-a.start))source=source.slice(0,e.start)+e.text+source.slice(e.end);return source;
  }}]});
try{
  const Panel=(await server.ssrLoadModule('/src/components/Tab4History/CmaIncomePanel.jsx')).default;
  const render=states=>{globalThis.__cmaState=states;return renderToStaticMarkup(React.createElement(Panel,{portfolioId:'p'}));};
  test('disabled feature exposes no query or write button',()=>{
    const html=render({data:{enabled:false}});
    assert.match(html,/운영 검증과 승인 후/);assert.doesNotMatch(html,/NH CMA 잔고 확인|CMA 이자로 반영/);
  });
  test('CMA interest preview separates cash increase from external contribution and preserves opt-in defaults',()=>{
    const html=render({data:{enabled:true,writes_enabled:true,automatic_ready:false,accounts:[{id:'cma',account_alias:'QA CMA'}],income:[],checks:[],interest_total_krw:'123'},
      aid:'cma',preview:{book_krw:'4800000',broker_krw:'4800123',interest_krw:'123'},confirmed:false});
    assert.match(html,/4,800,000 원/);assert.match(html,/4,800,123 원/);assert.match(html,/잔고 차액 123 원/);
    assert.match(html,/외부 투자금 입금으로 기록하지 않습니다/);assert.match(html,/09:00·12:00·15:40/);
    assert.doesNotMatch(html,/checked=""/);assert.match(html,/disabled=""[^>]*>CMA 이자로 반영/);
  });
  test('an unresolved income receipt only offers the same request retry',()=>{
    const html=render({data:{enabled:true,accounts:[],income:[],checks:[]},pending:{request_id:'pending-income'}});
    assert.match(html,/<details[^>]*open=""/);
    assert.match(html,/같은 이자 요청의 결과 확인/);assert.doesNotMatch(html,/NH CMA 잔고 확인|CMA 이자로 반영/);
  });
  test('zero deposit and full withdrawal availability remain review-only distinct balances',()=>{
    const html=render({data:{enabled:true,accounts:[],income:[],checks:[]},
      observation:{state:'ZERO_UNVERIFIED',observed_at:'2026-10-15T18:30:00+09:00',cash_krw:'0',sweep_krw:null,withdrawable_krw:'4800123'}});
    assert.match(html,/예수금 0 원/);assert.match(html,/CMA 상품 평가액 확인되지 않음/);
    assert.match(html,/출금가능금액 \(참고\) 4,800,123 원/);
    assert.match(html,/계좌 총잔고나 이자 확정액으로 사용하지 않습니다/);
    assert.doesNotMatch(html,/CMA 이자로 반영/);
  });
  test('older observations without a withdrawal field do not display a fabricated zero',()=>{
    const html=render({data:{enabled:true,accounts:[],income:[],checks:[]},
      observation:{state:'UNVERIFIED',observed_at:'2026-10-15T18:30:00+09:00'}});
    assert.match(html,/출금가능금액 \(참고\) 확인되지 않음/);
    assert.doesNotMatch(html,/출금가능금액 \(참고\) 0 원/);
  });
  test('read-only capability never offers an income write and disables automatic policy',()=>{
    const html=render({data:{enabled:true,writes_enabled:false,automatic_ready:false,accounts:[],income:[],checks:[]},aid:'cma',
      preview:{book_krw:'4800000',broker_krw:'4800123',interest_krw:'123'},confirmed:true});
    assert.match(html,/조회 전용 상태/);assert.match(html,/서버에서 차단/);
    assert.doesNotMatch(html,/>CMA 이자로 반영</);
    assert.match(html,/<input[^>]*disabled=""[^>]*\/?>이자 자동 반영/);
  });
  test('initial accrued difference is separated and cannot be posted as daily interest',()=>{
    const html=render({data:{enabled:true,writes_enabled:true,accounts:[],income:[],checks:[]},
      preview:{status:'INITIAL_BALANCE_REVIEW',book_krw:'1000',broker_krw:'1120',interest_krw:'120',paid_interest_krw:'20',prior_difference_krw:'100',can_apply:false}});
    assert.match(html,/오늘 지급 이자 20 원/);assert.match(html,/이전 차액 100 원/);
    assert.doesNotMatch(html,/>CMA 이자로 반영</);
  });
  test('initial correction is separate, gated and leaves paid interest pending',()=>{
    const state={data:{enabled:true,writes_enabled:true,automatic_ready:true,accounts:[],income:[],checks:[]},aid:'cma',
      preview:{status:'INITIAL_BALANCE_REVIEW',book_krw:'33936748',broker_krw:'33974558',interest_krw:'37810',
        paid_interest_krw:'2355',prior_difference_krw:'35455',can_apply:false}};
    const html=render(state);
    assert.match(html,/이전 누적 이자만 정리/);assert.match(html,/과거 지급일을 추정하지 않고/);
    assert.match(html,/disabled=""[^>]*>이전 누적 이자만 정리/);
    assert.doesNotMatch(html,/>CMA 이자로 반영</);
    const disabled=render({...state,data:{...state.data,writes_enabled:false}});
    assert.doesNotMatch(disabled,/>이전 누적 이자만 정리</);
  });
  test('swept CMA shows posted principal separately from unpaid valuation and withdrawal value',()=>{
    const html=render({data:{enabled:true,writes_enabled:true,automatic_ready:true,accounts:[],income:[],checks:[]},
      observation:{state:'CMA_PRINCIPAL_VERIFIED',observed_at:'2026-10-17T09:15:00+09:00',
        cash_krw:'0',sweep_krw:'1043',total_krw:'1043',withdrawable_krw:'1040',posted_krw:'1020',unposted_valuation_krw:'23'}});
    assert.match(html,/지급 완료 기준 장부 반영 잔액 1,020 원/);
    assert.match(html,/지급 확인 전 평가 차이 23 원/);assert.match(html,/이자로 반영하지 않습니다/);
  });
}finally{await server.close();globalThis.fetch=originalFetch;delete globalThis.__cmaState;}
