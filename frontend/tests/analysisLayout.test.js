import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const fixture = JSON.parse(await readFile(new URL('./fixtures/uiPresentation.json', import.meta.url), 'utf8'));
const server = await createServer({ root, logLevel: 'error', cacheDir: 'node_modules/.vite-test-analysis',
  server: { middlewareMode: true, watch: null, hmr: false, ws: false } });
const noop = () => {};
const data = { tracking: { baseline_date: '2026-10-05', baseline_value: 100, revision: 1 },
  snapshots: [{ snapshot_date: '2026-10-05', value_krw: 100 }], reports: [],
  flows: [{ id: 'one', event_date: '2026-10-05', account_id: fixture.bundle.accounts[0].id, amount_krw: 10, native_amount: 10, currency: 'KRW', voided: false }] };
const performance = { data, busy: false, error: '', notice: '', run: noop, capture: noop, setNotice: noop };
try {
  const Analysis = (await server.ssrLoadModule('/src/components/Tab6Analysis/AnalysisTab.jsx')).default;
  const Flows = (await server.ssrLoadModule('/src/components/Tab4History/ExternalCashFlowPanel.jsx')).default;
  const Chart = (await server.ssrLoadModule('/src/components/Tab6Analysis/PerformanceChart.jsx')).default;
  await test('chart offers accessible period and metric switches, real zero, missing reasons and unfinished labels', () => {
    const reports = [
      { kind: '월', label: '2026-01', start: '2026-01-01', end: '2026-01-31', return_pct: 0, profit: 0, partial: true, warning: '' },
      { kind: '월', label: '2026-02', start: '2026-01-31', end: '2026-02-28', return_pct: 2, profit: 10000, warning: '' },
      { kind: '월', label: '2026-03', start: '2026-02-28', end: '2026-03-10', return_pct: null, profit: null, warning: '경계일 평가액 없음' },
    ];
    const html = renderToStaticMarkup(React.createElement(Chart, { reports }));
    assert.match(html, /성과 그래프 기간/);
    assert.match(html, /성과 그래프 지표/);
    assert.match(html, /aria-label="2026-01 0.00%"/);
    assert.match(html, /aria-label="2026-03 계산 대기 · 경계일 평가액 없음"/);
    assert.match(html, /03\/10까지/);
    assert.match(html, /tabindex="0"/);
    assert.match(html, /수익률 \(%\)/);
    assert.match(html, /손익 \(원\)/);
  });
  await test('analysis shows chart and table first, management collapsed, without daily confirmation', () => {
    const html = renderToStaticMarkup(React.createElement(Analysis, { portfolioId: 'default', assets: fixture.bundle.assets,
      dashboardData: fixture.bundle.dashboard, performance, onOpenHistory: noop }));
    assert.match(html, /📈 기간 성과/);
    assert.match(html, /예금 만기 안내/);
    assert.match(html, /배당 계산 상세 보기/);
    assert.doesNotMatch(html, /기간 입출금 기록 확인 완료|시작 기준부터 최근 평가일까지/);
    assert.match(html, /<details><summary>기록 관리·수집 상태<\/summary>/);
    assert.match(html, /<details><summary>계산 방식·기록 범위 안내<\/summary>/);
    assert.ok(html.indexOf('기간 성과 그래프') < html.indexOf('기간 성과 표'));
    assert.ok(html.indexOf('기간 성과 표') < html.indexOf('기록 관리·수집 상태'));
    assert.match(html, /5\. 매매 및 입출금 기록으로 이동/);
    assert.doesNotMatch(html, /aria-label="입출금 금액"|기록 취소|기록 복원/);
  });
  await test('daily chart defaults to cumulative line view, exposes valuation and range, and renders a single zero point', () => {
    const dailyReports = [{ kind: '일', label: '2026-10-05', start: '2026-10-05', end: '2026-10-05',
      return_pct: 0, profit: 0, value_krw: 100, net_flow: 0, warning: '', partial: true, recorded_at: '2026-10-05T01:00:00Z' }];
    const html = renderToStaticMarkup(React.createElement(Chart, { reports: [], dailyReports, baselineDate: '2025-12-01' }));
    assert.match(html, /aria-pressed="true">일별 추이/);
    assert.match(html, /일별 누적/);
    assert.match(html, /평가액 \(원\)/);
    assert.match(html, /일별 그래프 표시 범위/);
    // A range containing only a recent record still shows the actual baseline.
    assert.match(html, /기준일 <time dateTime="2025-12-01">2025-12-01<\/time>/);
    assert.ok(html.indexOf('class="performance-chart-value"') < html.indexOf('class="performance-chart-scroll"'));
    assert.match(html, /시작 기준일부터의 누적 성과/);
    assert.match(html, /class="performance-chart-point"/);
    assert.match(html, /2026-10-05 기준일부터 누적 금액가중 수익률 0.00%/);
    assert.match(html, /점 하나가 표시/);
    assert.match(html, /마지막 기록 시각/);
    assert.match(html, /<details><summary>선택한 기록 상세<\/summary>/);
    assert.match(html, /<details><summary>그래프 보는 법<\/summary>/);
    assert.doesNotMatch(html, /NaN|Infinity/);
  });
  await test('recorded flows are identified without pending confirmation markers', () => {
    const dailyReports=[{kind:'일',label:'2026-10-06',start:'2026-10-05',end:'2026-10-06',
      return_pct:0,profit:0,value_krw:200,net_flow:100,flow_count:1,warning:''}];
    const html=renderToStaticMarkup(React.createElement(Chart,{dailyReports}));
    assert.match(html,/외부 입출금 1건 반영/);
    assert.doesNotMatch(html,/입출금 확인 전|잠정치/);
  });
  await test('verified closing baseline exposes dated sources and a preserved FX timestamp', () => {
    const dailyReports=[{kind:'일',label:'2026-10-05',start:'2026-10-05',end:'2026-10-05',
      return_pct:0,profit:0,value_krw:100,net_flow:0,record_kind:'baseline',baseline_kind:'closing_baseline',
      fx:{rate:1400,collected_at:'2026-10-05T06:46:00Z'},
      closes:[{id:'one',ticker:'VT',price_date:'2026-10-02',source:'검증된 종가'}]}];
    const html=renderToStaticMarkup(React.createElement(Chart,{dailyReports,baselineDate:'2026-10-05'}));
    assert.match(html,/종가 기준 시작 평가액/);
    assert.match(html,/2026-10-02/);
    assert.match(html,/원\/USD · 저장/);
    assert.doesNotMatch(html,/Invalid Date|시작 기준 등록 시점/);
  });
  await test('tab 4 panel owns external flow input, history and reversible cancellation', () => {
    const html = renderToStaticMarkup(React.createElement(Flows, { portfolioId: 'default', accounts: fixture.bundle.accounts, performance, onOpenAnalysis: noop }));
    assert.match(html, /aria-label="입출금 금액"/);
    assert.match(html, /외부 입출금 기록 저장/);
    assert.match(html, /기록 취소/);
    assert.match(html, /7\. 분석 및 확인에서 기간 성과 확인/);
    assert.doesNotMatch(html, /기간 입출금 기록 확인 완료/);
  });
  await test('initial cash input is available before establishing a positive performance baseline', () => {
    const html = renderToStaticMarkup(React.createElement(Flows, { portfolioId: 'default', accounts: [],
      performance: { ...performance, data: { tracking: null } }, onOpenAnalysis: noop }));
    assert.match(html, /아직 성과 시작 기준이 없습니다/);
    assert.match(html, /외부 입출금 기록 저장/);
    assert.match(html, /7\. 분석 및 확인에서 기간 성과 확인/);
  });
  await test('analysis keeps all three destinations visible when no assets exist', () => {
    const html = renderToStaticMarkup(React.createElement(Analysis, { portfolioId: 'empty', assets: [], dashboardData: {},
      performance: { ...performance, data: { tracking: null } }, onOpenHistory: noop }));
    assert.match(html, /기간 성과 시작 기준 등록/);
    assert.match(html, /등록된 예금이 없습니다/);
    assert.match(html, /현재 표시할 배당 계산 내역이 없습니다/);
  });
} finally { await server.close(); }
