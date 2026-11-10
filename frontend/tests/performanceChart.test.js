import test from 'node:test';
import assert from 'node:assert/strict';

test('closing lines cross verified holidays but break at missing trading sessions', () => {
  const series = dailyPerformanceSeries([
    {label:'2026-10-02',profit:0,record_kind:'close',previous_close_date:'2026-10-01'},
    {label:'2026-10-06',profit:1,record_kind:'close',previous_close_date:'2026-10-02'},
    {label:'2026-10-08',profit:2,record_kind:'close',previous_close_date:'2026-10-07'},
  ], 'profit', 'all');
  assert.deepEqual(dailyPerformanceSegments(series).map(s=>[s.from.label,s.to.label]), [['2026-10-02','2026-10-06']]);
});

test('baseline connects to first close over holidays but not across a missing session', () => {
  const rows=[{label:'2026-10-02',profit:0,record_kind:'baseline'},
    {label:'2026-10-06',profit:1,record_kind:'close',previous_close_date:'2026-10-02'}];
  assert.equal(dailyPerformanceSegments(dailyPerformanceSeries(rows,'profit','all')).length,1);
  rows[1]={...rows[1],label:'2026-10-07',previous_close_date:'2026-10-06'};
  assert.equal(dailyPerformanceSegments(dailyPerformanceSeries(rows,'profit','all')).length,0);
});
import { performanceSeries, performanceValue, performanceAxisValue, performanceScale, performanceDomain,
  dailyPerformanceSeries, dailyPerformanceSegments } from '../src/utils/performanceChart.js';

const row = (label, patch = {}) => ({ kind: '월', label, start: `${label}-01`, end: `${label}-28`, partial: false,
  return_pct: 2, profit: 120000, warning: '', ...patch });

test('chart separates monthly years and annual reports without modifying server data', () => {
  const reports = [row('2026-02'), row('2025-12'), row('2026-01'), row('2026', { kind: '연', end: '2026-12-31' })];
  const original = structuredClone(reports);
  assert.deepEqual(performanceSeries(reports, '월', 'return_pct', '2026').map(r => r.label), ['2026-01', '2026-02']);
  assert.deepEqual(performanceSeries(reports, '연', 'return_pct').map(r => r.label), ['2026']);
  assert.deepEqual(reports, original);
});

test('missing and nonfinite returns remain gaps while actual zero stays zero', () => {
  const series = performanceSeries([row('2026-01', { return_pct: null }), row('2026-02', { return_pct: 0 }),
    row('2026-03', { return_pct: NaN }), row('2026-04', { return_pct: Infinity }), row('2026-05', { return_pct: -1e-12 })], '월', 'return_pct', '2026');
  assert.deepEqual(series.map(r => r.value), [null, 0, null, null, 0]);
  assert.equal(performanceValue(null, 'return_pct'), '계산 대기');
  assert.equal(performanceValue(series[4].value, 'return_pct'), '0.00%');
});

test('profits use server results without interpreting legacy confirmation warnings', () => {
  const series = performanceSeries([row('2026-01', { return_pct: null, warning: '해당 기간의 외부 입출금 기록 확인이 필요합니다.' }),
    row('2026-02', { return_pct: null, warning: '입출금 부호가 여러 번 바뀜' }), row('2026-03', { profit: null, warning: '경계일 평가액 없음' })], '월', 'profit', '2026');
  assert.ok(series.every(r => !('provisional' in r)));
  assert.deepEqual(series.map(r => r.value), [120000, 120000, null]);
});

test('full periods, first partial periods and latest unfinished periods are distinguished including leap years', () => {
  const series = performanceSeries([row('2024-01', { end: '2024-01-31', partial: true }),
    row('2024-02', { end: '2024-02-29' }), row('2024-03', { end: '2024-03-10' })], '월', 'profit', '2024');
  assert.deepEqual(series.map(r => r.ongoing), [false, false, true]);
  assert.equal(series[0].partial, true);
  assert.equal(performanceSeries([row('2024', { kind: '연', end: '2024-12-31' })], '연', 'profit')[0].ongoing, false);
});

test('scale covers both signs and remains finite for all missing/zero values', () => {
  assert.equal(performanceScale([{ value: 2.2 }, { value: -6 }], 'return_pct'), 10);
  assert.equal(performanceScale([{ value: null }, { value: 0 }], 'return_pct'), 1);
  assert.equal(performanceScale([], 'profit'), 100000);
  assert.equal(performanceValue(-1234567, 'profit'), '-1,234,567 원');
  assert.equal(performanceValue(120000, 'profit', true), '+12만 원');
});

const dailyRow = (label, patch = {}) => ({ kind: '일', label, start: '2025-12-01', end: label,
  return_pct: 2, profit: 1000, value_krw: 101000, warning: '', ...patch });

test('daily range crosses years and is anchored on last recorded date, preserving cumulative baseline', () => {
  const reports = [dailyRow('2026-01-02'), dailyRow('2025-12-03'), dailyRow('2025-12-04')];
  const original = structuredClone(reports);
  const series = dailyPerformanceSeries(reports, 'return_pct', '30');
  assert.deepEqual(series.map(r => r.label), ['2025-12-04', '2026-01-02']);
  assert.equal(series[0].start, '2025-12-01');
  assert.equal(dailyPerformanceSeries(reports, 'return_pct', 'all').length, 3);
  assert.deepEqual(reports, original);
});

test('opening profit shifts the cumulative series but preserves gaps and daily changes', () => {
  const reports = [
    dailyRow('2026-10-05', {profit:0,twr_pct:0,value_krw:10000000}),
    dailyRow('2026-10-06', {profit:31111,twr_pct:0.31,value_krw:10031111}),
    dailyRow('2026-10-07', {profit:null,twr_pct:null,ledger_unconfirmed:true}),
  ];
  const openingLoss = -639000;
  const shifted = dailyPerformanceSeries(reports,'profit','all',openingLoss);
  assert.deepEqual(shifted.map(row => row.value),[-639000,-607889,null]);
  assert.deepEqual(shifted.map(row => row.profit),[0,31111,null]);
  assert.deepEqual(shifted.map(row => row.comparison?.profit),[undefined,31111,null]);
  for (const metric of ['value_krw','twr_pct']) {
    assert.deepEqual(dailyPerformanceSeries(reports,metric,'all',openingLoss),
      dailyPerformanceSeries(reports,metric,'all'));
  }
});

test('daily comparison removes external flows through cumulative profit and crosses a weekend', () => {
  const reports = [
    dailyRow('2026-11-06', { value_krw: 10000000, net_flow: 0, profit: -1500000, record_kind: 'close' }),
    dailyRow('2026-11-09', { value_krw: 11123194, net_flow: 1000000, profit: -1376806,
      return_pct: null, record_kind: 'close', previous_close_date: '2026-11-06' }),
    dailyRow('2026-11-10', { value_krw: 10623194, net_flow: 500000, profit: -1376806,
      record_kind: 'close', previous_close_date: '2026-11-09' }),
  ];
  const [first, monday, tuesday] = dailyPerformanceSeries(reports, 'return_pct', 'all');
  assert.equal(first.comparison, null);
  assert.equal(monday.value, null);
  assert.deepEqual(monday.comparison, {date:'2026-11-06', consecutive:true, profit:123194});
  assert.equal(monday.profit, -1376806);
  assert.equal(tuesday.comparison.profit, 0);
});

test('daily comparison uses records outside the plot range and respects missing or masked amounts', () => {
  const reports = [
    dailyRow('2026-10-09', { profit: 900, record_kind: 'close' }),
    dailyRow('2026-10-13', { profit: 1000, record_kind: 'close', previous_close_date: '2026-10-12' }),
    dailyRow('2026-11-11', { profit: null }),
    dailyRow('2026-11-12', { profit: 2000 }),
    dailyRow('2026-11-13', { start:'2026-11-12', profit:2100 }),
  ];
  const [first, gap, masked, afterMask, otherBaseline] = dailyPerformanceSeries(reports, 'profit', 'all');
  assert.equal(first.comparison, null);
  assert.deepEqual(gap.comparison, {date:'2026-10-09', consecutive:false, profit:100});
  assert.equal(masked.comparison.profit, null);
  assert.equal(afterMask.comparison.profit, null);
  assert.equal(otherBaseline.comparison.profit, null);
  const visible = dailyPerformanceSeries(reports.slice(0, -1), 'profit', '31');
  assert.equal(visible[0].label, '2026-10-13');
  assert.equal(visible[0].comparison.date, '2026-10-09');
});

test('daily lines break at missing dates and null results, connect genuine zero and cross leap day', () => {
  const series = dailyPerformanceSeries([dailyRow('2024-02-28', { return_pct: 0 }), dailyRow('2024-02-29'),
    dailyRow('2024-03-01'), dailyRow('2024-03-03'), dailyRow('2024-03-04', { return_pct: null }),
    dailyRow('2024-03-05'), dailyRow('2024-03-06')], 'return_pct', 'all');
  assert.deepEqual(dailyPerformanceSegments(series).map(s => [s.from.label, s.to.label]),
    [['2024-02-28', '2024-02-29'], ['2024-02-29', '2024-03-01'], ['2024-03-05', '2024-03-06']]);
  assert.deepEqual(dailyPerformanceSegments([]), []);
  assert.deepEqual(dailyPerformanceSegments([series[0]]), []);
});

test('profit lines and valuations have no confirmation markers, missing returns stay absent', () => {
  const rows = [dailyRow('2026-01-01'), dailyRow('2026-01-02', { return_pct: null, warning: '外' }),
    dailyRow('2026-01-03', { return_pct: null, warning: '해당 기간의 외부 입출금 기록 확인이 필요합니다.' })];
  const profits = dailyPerformanceSeries(rows, 'profit', 'all');
  assert.ok(profits.every(r => !('provisional' in r)));
  assert.equal(dailyPerformanceSegments(profits).length,2);
  assert.ok(dailyPerformanceSeries(rows, 'value_krw').every(r => r.value === 101000));
  assert.deepEqual(dailyPerformanceSeries(rows, 'return_pct').map(r => r.value), [2, null, null]);
});

test('valuation axis zooms around real values, has a finite span for a single point or zero, and shows unsigned values', () => {
  const [min, max] = performanceDomain([{ value: 1000000 }, { value: 1010000 }], 'value_krw');
  assert.ok(min > 0 && min < 1000000 && max > 1010000);
  assert.deepEqual(performanceDomain([{ value: 0 }], 'value_krw'), [0, 1]);
  assert.deepEqual(performanceDomain([], 'value_krw'), [0, 100000]);
  assert.deepEqual(performanceDomain([{ value: -6 }], 'return_pct'), [-10, 10]);
  assert.equal(performanceValue(100000, 'value_krw'), '100,000 원');
  assert.equal(performanceValue(100000, 'value_krw', true), '10만 원');
});

test('small valuation changes remain visible even in a large portfolio', () => {
  const low = 103300000, high = 103345000;
  const [min, max] = performanceDomain([{value: low}, {value: high}], 'value_krw');
  assert.deepEqual([min, max], [low - 4500, high + 4500]);
  assert.ok((high - low) / (max - min) > 0.8);
  const ticks = [0,0.25,0.5,0.75,1].map(f => performanceAxisValue(min + f * (max - min), 'value_krw', max - min));
  assert.equal(new Set(ticks).size, 5);
  assert.ok(ticks.every(label => label.endsWith('만 원')));
  const flat = performanceDomain([{value: high}, {value: high}], 'value_krw');
  assert.ok(flat[0] < high && flat[1] > high && Number.isFinite(flat[1] - flat[0]));
});
