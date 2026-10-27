import test from 'node:test';
import assert from 'node:assert/strict';
import {holdingCurrent,holdingSeries,holdingDomain,holdingSegments,holdingValue} from '../src/utils/holdingHistory.js';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
const now=new Date('2026-10-27T09:00:00Z');
test('live point uses the exact dashboard KPI and does not derive a new denominator',()=>{
  const kpi={total_stock_buy:100,total_stock_profit:9,total_stock_return:9.004,total_portfolio_eval:500};
  const m=holdingCurrent(kpi);assert.equal(m.profit_krw,9);assert.equal(m.return_pct,9.004);assert.equal(m.value_krw,500);
  assert.equal(holdingCurrent({}),null);
});
test('current observation stays distinct from same-day close; Korean date is used',()=>{
  const series=holdingSeries([{date:'2026-10-27',profit_krw:5}],{profit_krw:7},{now});
  assert.deepEqual(series.map(r=>r.key),['2026-10-27','current']);assert.equal(series[1].label,'현재');
});
test('missing values break lines instead of connecting or showing zero',()=>{
  const series=[{profit_krw:1},{profit_krw:null},{profit_krw:3},{profit_krw:4,current:true}];
  assert.deepEqual(holdingSegments(series,'profit_krw'),[{from:2,to:3,live:true}]);
  assert.equal(holdingValue(null,'profit_krw'),'기록 부족');
});
test('month/year selection is a level at the last recorded date, not summed profit',()=>{
  const rows=[{date:'2026-09-30',profit_krw:5},{date:'2026-10-06',profit_krw:10},{date:'2026-10-27',profit_krw:12}];
  assert.deepEqual(holdingSeries(rows,null,{period:'month',range:'all',now}).map(r=>r.profit_krw),[5,12]);
  assert.deepEqual(holdingSeries(rows,null,{period:'year',range:'all',now}).map(r=>r.profit_krw),[12]);
});
test('axis zooms to visible levels and handles zero/no data',()=>{
  const [lo,hi]=holdingDomain([{value_krw:100000000},{value_krw:100100000}],'value_krw');assert.ok(lo>0&&hi>100100000);
  assert.deepEqual(holdingDomain([],'profit_krw'),[-1,1]);
  const [a,b]=holdingDomain([{profit_krw:0}],'profit_krw');assert.ok(a<0&&b>0);
});

const originalFetch=globalThis.fetch;
globalThis.fetch=()=>{throw Error('Rendering holding history must not call external APIs');};
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,configFile:false,
  logLevel:'error',cacheDir:'node_modules/.vite-test-holding-history',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try{
  const Panel=(await server.ssrLoadModule('/src/components/Tab6Analysis/HoldingsPerformance.jsx')).default;
  test('shared panel exposes a nonzero first profit and distinguishes the current value without a zero-start baseline',()=>{
    const html=renderToStaticMarkup(React.createElement(Panel,{scope:'p',initialData:{rows:[{date:'2026-10-05',status:'COMPLETE',profit_krw:3000000,return_pct:5,cost_krw:60000000,value_krw:65000000}]},
      current:{status:'COMPLETE',profit_krw:4000000,return_pct:6,cost_krw:65000000,value_krw:71000000}}));
    assert.match(html,/3,000,000원/);assert.match(html,/4,000,000원/);assert.match(html,/현재 · 조회 시점/);
    assert.match(html,/기록 범위/);assert.match(html,/tabindex="0"/);
  });
}finally{await server.close();globalThis.fetch=originalFetch;}
