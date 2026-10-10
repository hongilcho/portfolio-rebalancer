import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {parseSync} from 'rolldown/experimental';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {performanceChartLayout,nearestPerformanceRecord,dailyPerformanceSegments} from '../src/utils/performanceChart.js';
import {accountIssues,remainingAnnualLimit} from '../src/utils/accountPresentation.js';
const fixture=JSON.parse(await readFile(new URL('./fixtures/uiPresentation.json',import.meta.url),'utf8'));
const original={matchMedia:globalThis.matchMedia,localStorage:globalThis.localStorage,sessionStorage:globalThis.sessionStorage,fetch:globalThis.fetch};
globalThis.localStorage=globalThis.sessionStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{}};
globalThis.fetch=()=>{throw new Error('Mobile synthetic tests cannot call real APIs');};
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,logLevel:'error',cacheDir:'node_modules/.vite-test-mobile',server:{middlewareMode:true,watch:null,hmr:false,ws:false},plugins:[{name:'responsive-seeds',enforce:'pre',transform(source,id,options){
  if(!options?.ssr || !/(PerformanceChart|App|AccountsTab)\.jsx$/.test(id))return;
  const {program,errors}=parseSync(id,source);assert.equal(errors.length,0);const edits=[];
  const walk=node=>{if(!node || typeof node!=='object')return;
    if(node.type==='VariableDeclarator' && node.id.type==='ArrayPattern' && node.init?.callee?.name==='useState'){
      const key=node.id.elements[0]?.name,arg=node.init.arguments[0];if(arg)edits.push({start:arg.start,end:arg.end,text:`(Object.hasOwn(globalThis.__mobileStates,'${key}')?globalThis.__mobileStates.${key}:(${source.slice(arg.start,arg.end)}))`});
    }
    for(const value of Object.values(node))if(Array.isArray(value))value.forEach(walk);else if(value && typeof value==='object')walk(value);
  };walk(program);for(const e of edits.sort((a,b)=>b.start-a.start))source=source.slice(0,e.start)+e.text+source.slice(e.end);return source;
}}]});
const dailyReports=Array.from({length:90},(_,i)=>{const label=new Date(Date.UTC(2026,6,1+i)).toISOString().slice(0,10);return {kind:'일',label,start:label,end:label,value_krw:100000000+i*1000,return_pct:i/100,profit:i*1000,record_kind:'legacy'};});
try{
  const modules={};for(const [key,path] of Object.entries({Dashboard:'/src/components/Tab1Dashboard/DashboardTab.jsx',Accounts:'/src/components/Tab2Accounts/AccountsTab.jsx',Chart:'/src/components/Tab6Analysis/PerformanceChart.jsx',App:'/src/App.jsx'}))modules[key]=(await server.ssrLoadModule(path)).default;
  const render=(Component,props,states={},mobile=true)=>{globalThis.matchMedia=()=>({matches:mobile});globalThis.__mobileStates=states;return renderToStaticMarkup(React.createElement(Component,props));};
  test('eight ordered destinations retain existing navigation ids and cross-links',()=>{
    const html=render(modules.App,{}, {isAuthenticated:true,loading:false,dashboardData:fixture.bundle.dashboard,assets:fixture.bundle.assets,accounts:fixture.bundle.accounts});
    const selector=html.match(/<select[^>]*aria-label="포트폴리오 화면 선택"[\s\S]*?<\/select>/)[0];
    for(const label of ['1. 포트폴리오 현황','2. 계좌 현황 및 한도','3. 목표 비중 설정','4. 리밸런싱 전략','5. 매매 및 입출금 기록','6. 계좌 마스터 관리','7. 분석 및 확인','8. 투자 실행'])assert.ok(selector.includes(label),label);
    assert.ok(selector.indexOf('2. 계좌')<selector.indexOf('3. 목표'));
  });
  test('mobile overview shows meaningful totals and collapses detail; account lists have moved out',()=>{
    const html=render(modules.Dashboard,{dashboardData:fixture.bundle.dashboard,assets:fixture.bundle.assets});
    assert.match(html,/포트폴리오 핵심 요약/);assert.match(html,/예수금 포함/);
    assert.match(html,/<details class="mobile-summary-detail"><summary>원금·배당·통화별 상세보기/);
    assert.match(html,/<details[^>]*class="mobile-card-item asset-disclosure"/);
    assert.doesNotMatch(html,/계좌 현황 및 한도|account-accordion/);
    assert.match(html,/자산군별 비중/);
  });
  test('account cards start collapsed on phones, keep exceptions visible, and retain desktop detail',()=>{
    const account={id:'qa',account_alias:'QA ISA',account_no:'QA-001',account_type:'IRP',deposit_krw:-1,deposit_usd:0,risk_pct:80,total_val:100000,annual_limit:2000000,annual_limit_pct:.25,holdings:[]};
    const props={dashboardData:{account_summaries:[account]}};
    const mobile=render(modules.Accounts,props);
    assert.match(mobile,/aria-expanded="false"/);assert.doesNotMatch(mobile,/class="accordion-body"/);
    assert.match(mobile,/음수 예수금 확인 필요/);assert.match(mobile,/IRP 위험자산 70% 초과/);assert.match(mobile,/연간 남은 납입한도 1,500,000 원/);
    const expanded=render(modules.Accounts,props,{expandedAccs:{qa:true}});assert.match(expanded,/class="accordion-body"/);assert.match(expanded,/계좌번호 QA-001/);
    const desktop=render(modules.Accounts,props,{},false);assert.match(desktop,/aria-expanded="true"/);assert.match(desktop,/class="accordion-body"/);
  });
  test('360/390/430 phone chart widths fit both 90 daily points and twelve monthly bars without min-width',()=>{
    const reports=Array.from({length:12},(_,i)=>({kind:'월',label:`2026-${String(i+1).padStart(2,'0')}`,start:'2026-01-01',end:'2026-12-31',return_pct:i,profit:i*1000}));
    for(const viewport of [360,390,430]){
      const containerWidth=viewport-72;
      for(const kind of ['일','월']){
        const html=render(modules.Chart,{dailyReports,reports,baselineDate:'2026-07-01'},{containerWidth,kind,range:'all'});
        assert.match(html,new RegExp(`viewBox="0 0 ${containerWidth} 260"`));assert.doesNotMatch(html,/min-width|좌우로 이동|width:1000/);
        assert.ok(performanceChartLayout(containerWidth).right<=containerWidth);
      }
    }
  });
  test('compressed selection preserves exact record and missing-day gaps rather than aggregating values',()=>{
    const series=dailyReports.slice(0,3);const {left,right}=performanceChartLayout(288);
    assert.equal(nearestPerformanceRecord(series,left,left,right,true),series[0]);
    assert.equal(nearestPerformanceRecord(series,(left+right)/2,left,right,true),series[1]);
    assert.equal(nearestPerformanceRecord(series,right,left,right,true),series[2]);
    assert.equal(nearestPerformanceRecord([],0,left,right,true),null);
    assert.equal(dailyPerformanceSegments([{...series[0],value:1},{...series[2],value:2}]).length,0);
    assert.deepEqual(accountIssues({deposit_krw:0,deposit_usd:0}),[]);assert.equal(remainingAnnualLimit({annual_limit:100}),null);
  });
}finally{await server.close();Object.assign(globalThis,original);delete globalThis.__mobileStates;}
