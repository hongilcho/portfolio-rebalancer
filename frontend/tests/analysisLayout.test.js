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
  await test('analysis combines three panels and confirmation, with flow editing in tab 4 only', () => {
    const html = renderToStaticMarkup(React.createElement(Analysis, { portfolioId: 'default', assets: fixture.bundle.assets,
      dashboardData: fixture.bundle.dashboard, performance, onOpenHistory: noop }));
    assert.match(html, /월별·연간 기간 성과/);
    assert.match(html, /예금 만기 안내/);
    assert.match(html, /배당 계산 상세 보기/);
    assert.match(html, /기간 입출금 기록 확인 완료/);
    assert.match(html, /4\. 매매 및 입출금 기록으로 이동/);
    assert.doesNotMatch(html, /aria-label="입출금 금액"|기록 취소|기록 복원/);
  });
  await test('tab 4 panel owns external flow input, history and reversible cancellation', () => {
    const html = renderToStaticMarkup(React.createElement(Flows, { portfolioId: 'default', accounts: fixture.bundle.accounts, performance, onOpenAnalysis: noop }));
    assert.match(html, /aria-label="입출금 금액"/);
    assert.match(html, /외부 입출금 기록 저장/);
    assert.match(html, /기록 취소/);
    assert.match(html, /6\. 분석 및 확인에서 기간 성과 확인/);
    assert.doesNotMatch(html, /기간 입출금 기록 확인 완료/);
  });
  await test('tab 4 directs an unregistered portfolio to the explicit baseline in tab 6', () => {
    const html = renderToStaticMarkup(React.createElement(Flows, { portfolioId: 'default', accounts: [],
      performance: { ...performance, data: { tracking: null } }, onOpenAnalysis: noop }));
    assert.match(html, /6\. 분석 및 확인으로 이동/);
    assert.doesNotMatch(html, /외부 입출금 기록 저장|aria-label="입출금 금액"/);
  });
  await test('analysis keeps all three destinations visible when no assets exist', () => {
    const html = renderToStaticMarkup(React.createElement(Analysis, { portfolioId: 'empty', assets: [], dashboardData: {},
      performance: { ...performance, data: { tracking: null } }, onOpenHistory: noop }));
    assert.match(html, /기간 성과 시작 기준 등록/);
    assert.match(html, /등록된 예금이 없습니다/);
    assert.match(html, /현재 표시할 배당 계산 내역이 없습니다/);
  });
} finally { await server.close(); }
