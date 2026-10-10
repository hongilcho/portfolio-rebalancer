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
 test('first empty entry is safe and future income defaults to zero',()=>{const html=render(Workspace,props);assert.match(html,/이 계획에 사용할 자금 확인/);assert.match(html,/aria-label="추가 투자 입금액"[^>]*value="0"/);assert.doesNotMatch(html,/value="isa"/);});
 test('unready backend limits only the new workspace and offers retry',()=>{const html=render(Workspace,{...props,model:{...props.model,available:false,error:'Render 배포 필요'}});assert.match(html,/지원 여부 다시 확인/);assert.doesNotMatch(html,/확인한 계획으로 투자 시작/);});
 test('controlled execution input keeps task header and hides workflow lists',()=>{const html=render(Execution,{cycle,recordingStepId:'buy',compactWhileInput:true,renderInput:()=>null});assert.match(html,/aria-label="투자 결과 입력"/);assert.doesNotMatch(html,/class="section-card execution-list"/);assert.match(html,/투자 진행으로 돌아가기/);});
 test('refreshing investment data cannot offer writes against the displayed old version',()=>{const html=render(Workspace,{...props,model:{...props.model,cycle,loading:true}});assert.match(html,/<button[^>]*execution-record[^>]*disabled/);assert.match(html,/<button[^>]*disabled[^>]*>잠시 중단/);});
 test('task input links automatically and only exposes relevant inputs',()=>{const html=render(History,{accounts,assets:[],priceMap:{},embedded:true,currentPortfolioId:'default',executionContext:{cycle_id:'c',revision:1,portfolio_id:'default',name:'적립 투자',step,steps:[step]}});assert.match(html,/체결 알림 붙여넣기/);assert.match(html,/5번 장부에 기록/);assert.doesNotMatch(html,/현재 입력을 이 투자|연결 없이|직접 입력 종류|ledger-correction-panel|달러 원가·환전 관리/);});
 test('ordinary history is independent of any investment cycle',()=>{const html=render(History,{accounts,assets:[],priceMap:{},currentPortfolioId:'default'});assert.match(html,/aria-label="5번 탭 작업"/);assert.doesNotMatch(html,/투자 회차의 실행 실적|현재 입력을 이 투자/);});
 test('workflow presents new recording and existing journal import as two clear paths',()=>{const html=render(Execution,{cycle,onRecord:()=>{},renderExistingRecords:()=>null});assert.match(html,/새 체결 내역 입력/);assert.match(html,/기록한 거래 가져오기/);});

 test('new funding setup exposes one percent buffers behind details',()=>{const html=render(Workspace,props);assert.match(html,/여유자금 설정/);assert.match(html,/aria-label="가격 여유율"[^>]*value="1"/);assert.match(html,/aria-label="환율 여유율"[^>]*value="1"/);});
 test('investment summary shows actual targets and hides recurring instructions in details',()=>{const html=render(Execution,{cycle});assert.match(html,/aria-label="투자 요약"/);assert.match(html,/채권/);assert.match(html,/목표 20/);assert.doesNotMatch(html,/이번 투자 안내/);assert.match(html,/입력 방법과 장부 처리 안내/);});
 test('only closed purchase investments offer CMA recovery planning',()=>{const closed={...cycle,status:'CLOSED',payload:{representative_account_id:'cma'}};const html=render(Workspace,{...props,model:{...props.model,cycle:closed}});assert.match(html,/남은 현금 CMA 회수 계획 만들기/);assert.doesNotMatch(render(Workspace,{...props,model:{...props.model,cycle:{...closed,plan_type:'CASH_RETURN'}}}),/남은 현금 CMA 회수 계획 만들기/);});

}finally{globalThis.fetch=fetch;await server.close();}
