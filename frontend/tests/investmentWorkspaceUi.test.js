import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,logLevel:'error',cacheDir:'node_modules/.vite-test-investment-workspace',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
const fetch=globalThis.fetch;globalThis.fetch=()=>{throw new Error('No network during synthetic SSR');};
try{
 const Workspace=(await server.ssrLoadModule('/src/components/Tab8Execution/InvestmentWorkspace.jsx')).default;
 const History=(await server.ssrLoadModule('/src/components/Tab4History/HistoryTab.jsx')).default;
 const Execution=(await server.ssrLoadModule('/src/components/Tab8Execution/ExecutionTab.jsx')).default;
 const accounts=[{id:'cma',account_alias:'CMA',account_type:'CMA',deposit_krw:1150000},{id:'isa',account_alias:'ISA',account_type:'ISA'}];
 const step={id:'buy',kind:'BUY',title:'채권 매수',account_id:'isa',account_alias:'ISA',asset_id:'bond',asset_name:'채권',currency:'KRW',target_quantity:20,depends_on:[]};
 const cycle={id:'c',name:'적립 투자',status:'ACTIVE',revision:1,steps:[step],results:[],budget_krw:180000};
 const props={portfolioId:'default',accounts,usdKrw:1400,model:{cycle:null,history:[],plans:[],loading:false,error:'',available:true}};
 const render=(C,p)=>renderToStaticMarkup(React.createElement(C,p));
 test('first empty entry is safe and future income defaults to zero',()=>{const html=render(Workspace,props);assert.match(html,/이번 투자 시작/);assert.match(html,/aria-label="추가 투자 입금액"[^>]*value="0"/);assert.doesNotMatch(html,/value="isa"/);});
 test('unready backend limits only the new workspace and offers retry',()=>{const html=render(Workspace,{...props,model:{...props.model,available:false,error:'Render 배포 필요'}});assert.match(html,/지원 여부 다시 확인/);assert.doesNotMatch(html,/확인한 계획으로 투자 시작/);});
 test('controlled execution input keeps task header and hides workflow lists',()=>{const html=render(Execution,{cycle,recordingStepId:'buy',compactWhileInput:true,renderInput:()=>null});assert.match(html,/aria-label="투자 결과 입력"/);assert.doesNotMatch(html,/class="section-card execution-list"/);assert.match(html,/진행 화면으로/);});
 test('refreshing investment data cannot offer writes against the displayed old version',()=>{const html=render(Workspace,{...props,model:{...props.model,cycle,loading:true}});assert.match(html,/<button[^>]*execution-record[^>]*disabled/);assert.match(html,/<button[^>]*disabled[^>]*>잠시 중단/);});
 test('embedded shared history keeps the common NH form and requires explicit connection consent',()=>{const html=render(History,{accounts,assets:[],priceMap:{},embedded:true,currentPortfolioId:'default',executionContext:{cycle_id:'c',revision:1,portfolio_id:'default',name:'적립 투자',step,steps:[step]}});assert.match(html,/NH 알림 붙여넣기/);assert.match(html,/현재 입력을 이 투자에 연결함을 확인/);assert.doesNotMatch(html,/aria-label="5번 탭 작업"/);assert.match(html,/<details hidden=""[^>]*ledger-correction-panel/);assert.match(html,/과거 누락·잔고 정정은 5번에서 처리/);});
}finally{globalThis.fetch=fetch;await server.close();}
