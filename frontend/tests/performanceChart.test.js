import test from 'node:test';
import assert from 'node:assert/strict';
import { performanceSeries, performanceValue, performanceScale } from '../src/utils/performanceChart.js';

const row = (label, patch = {}) => ({ kind: '월', label, start: `${label}-01`, end: `${label}-28`, partial: false,
  return_pct: 2, profit: 120000, warning: '', ...patch });

test('chart separates monthly years and annual reports without modifying server data', () => {
  const reports = [row('2026-02'), row('2025-12'), row('2026-01'), row('2026', { kind: '연', end: '2026-12-31' })];
  const original = structuredClone(reports);
  assert.deepEqual(performanceSeries(reports, '월', 'return_pct', '2026').map(r => r.label), ['2026-01', '2026-02']);
  assert.deepEqual(performanceSeries(reports, '연', 'return_pct').map(r => r.label), ['2026']);
  assert.deepEqual(reports, original);
});

test('missing, unconfirmed, and nonfinite returns remain gaps while actual zero stays zero', () => {
  const series = performanceSeries([row('2026-01', { return_pct: null }), row('2026-02', { return_pct: 0 }),
    row('2026-03', { return_pct: NaN }), row('2026-04', { return_pct: Infinity }), row('2026-05', { return_pct: -1e-12 })], '월', 'return_pct', '2026');
  assert.deepEqual(series.map(r => r.value), [null, 0, null, null, 0]);
  assert.equal(performanceValue(null, 'return_pct'), '계산 대기');
  assert.equal(performanceValue(series[4].value, 'return_pct'), '0.00%');
});

test('profits before flow confirmation are marked provisional; a return-specific warning does not invalidate profit', () => {
  const series = performanceSeries([row('2026-01', { return_pct: null, warning: '해당 기간의 외부 입출금 기록 확인이 필요합니다.' }),
    row('2026-02', { return_pct: null, warning: '입출금 부호가 여러 번 바뀜' }), row('2026-03', { profit: null, warning: '경계일 평가액 없음' })], '월', 'profit', '2026');
  assert.deepEqual(series.map(r => r.provisional), [true, false, false]);
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
