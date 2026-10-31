import test from 'node:test';
import assert from 'node:assert/strict';
import {profitTone,splitProfitSegment,zeroReference,signedProfit} from '../src/utils/profitChartSignals.js';
import {holdingDomain,holdingSegments} from '../src/utils/holdingHistory.js';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

test('zero crossing splits at the interpolated zero, independent of movement direction',()=>{
 const parts=splitProfitSegment({x:10,value:-30},{x:90,value:10});
 assert.equal(parts.length,2);assert.deepEqual(parts[0].to,{x:70,value:0});assert.deepEqual(parts[1].from,parts[0].to);
 assert.equal(parts[0].color,'var(--color-loss)');assert.equal(parts[1].color,'var(--color-profit)');
 const reverse=splitProfitSegment({x:10,value:30},{x:90,value:-10});assert.equal(reverse[0].color,'var(--color-profit)');assert.equal(reverse[1].color,'var(--color-loss)');
});
test('rising losses stay blue and falling profits stay red; zero endpoints do not add extra parts',()=>{
 assert.equal(splitProfitSegment({x:0,value:-5},{x:1,value:-1})[0].color,'var(--color-loss)');
 assert.equal(splitProfitSegment({x:0,value:5},{x:1,value:1})[0].color,'var(--color-profit)');
 assert.equal(splitProfitSegment({x:0,value:0},{x:1,value:-1}).length,1);
 assert.equal(splitProfitSegment({x:0,value:0},{x:1,value:0})[0].color,'var(--text-secondary)');
});
test('missing observations never become zero or a connected segment',()=>{
 assert.equal(profitTone(null),'unknown');assert.equal(profitTone(NaN),'unknown');assert.equal(profitTone(0),'zero');
 assert.deepEqual(splitProfitSegment({x:0,value:null},{x:1,value:1}),[]);
 assert.deepEqual(holdingSegments([{profit_krw:-1},{profit_krw:null},{profit_krw:2}],'profit_krw'),[]);
});
test('zero reference respects the existing zoom, skips NAV and absent values',()=>{
 const rows=[{profit_krw:4000000},{profit_krw:4070000}],domain=holdingDomain(rows,'profit_krw');assert.ok(domain[0]>0);
 assert.equal(zeroReference(...domain,'profit_krw',rows.map(r=>r.profit_krw)).position,'below');
 assert.equal(zeroReference(-5,-1,'return_pct',[-4,-2]).position,'above');
 assert.equal(zeroReference(-1,1,'return_pct',[0]).label,'손익분기점 0%');
 assert.equal(zeroReference(-1,1,'value_krw',[1]),null);assert.equal(zeroReference(-1,1,'profit_krw',[null]),null);
});
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,configFile:false,logLevel:'error',cacheDir:'node_modules/.vite-test-profit-signals',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try{
 const Panel=(await server.ssrLoadModule('/src/components/Tab6Analysis/HoldingsPerformance.jsx')).default;
 const Period=(await server.ssrLoadModule('/src/components/Tab6Analysis/PerformanceChart.jsx')).default;
 const {ProfitStatus}=await server.ssrLoadModule('/src/components/common/ProfitChartSignals.jsx');
 test('real holding panel renders profit/loss colors, named zero and stable current status',()=>{
  const html=renderToStaticMarkup(React.createElement(Panel,{scope:'crypto',initialData:{rows:[{date:'2026-10-29',profit_krw:-100,return_pct:-1,status:'COMPLETE'}]},current:{profit_krw:100,return_pct:1,status:'COMPLETE'}}));
  assert.match(html,/현재 손익 상태/);assert.match(html,/손익분기점 0원/);assert.match(html,/stroke="var\(--color-loss\)"/);assert.match(html,/stroke="var\(--color-profit\)"/);
  assert.match(html,/매일 오후 4시 기준/);assert.match(html,/현재 · 조회 시점/);
 });
 test('all-negative and missing panels explain loss or unavailable values without inventing a zero',()=>{
  const html=renderToStaticMarkup(React.createElement(Panel,{scope:'p',initialData:{rows:[]},current:{profit_krw:-530000,return_pct:-.53}}));
  assert.match(html,/표시 구간 전체 손실/);assert.match(html,/−530,000원/);assert.doesNotMatch(html,/class="profit-chart-zero-line"/);
  const missing=renderToStaticMarkup(React.createElement(ProfitStatus,{profit:null,rate:null,caption:'현재'}));assert.match(missing,/확인 필요/);assert.doesNotMatch(missing,/손익분기/);
 });
 test('period graph uses the same signed cues without replacing its performance definition',()=>{
  const html=renderToStaticMarkup(React.createElement(Period,{baselineDate:'2026-10-05',dailyReports:[{kind:'일',label:'2026-10-29',profit:-100,return_pct:-1,record_kind:'close',previous_close_date:'2026-10-28'},{kind:'일',label:'2026-10-30',profit:100,return_pct:1,record_kind:'close',previous_close_date:'2026-10-29'}]}));
  assert.match(html,/손익분기점 0%/);assert.match(html,/최근 기록 · 2026-10-30/);assert.match(html,/기준일부터 누적/);assert.match(html,/stroke="var\(--color-loss\)"/);assert.match(html,/stroke="var\(--color-profit\)"/);
 });
 test('small nonzero values and missing rates are not presented as exact breakeven',()=>{
  assert.equal(signedProfit(-.001,'return_pct'),'−0.01% 미만');assert.equal(signedProfit(.1,'profit'),'+1원 미만');assert.equal(signedProfit(null,'profit'),'기록 부족');
 });
}finally{await server.close();}
