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
import { performanceSeries, performanceValue, performanceScale, performanceDomain,
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
