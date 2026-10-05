import { formatKRW } from './formatters.js';

export function performanceSeries(reports, kind, metric, year) {
  return reports.filter(row => row.kind === kind && (kind !== '월' || row.label.startsWith(`${year}-`)))
    .sort((a, b) => a.label.localeCompare(b.label)).map(row => {
      const raw = row[metric];
      const value = typeof raw === 'number' && Number.isFinite(raw)
        ? metric === 'return_pct' ? (Math.abs(raw) < 0.005 ? 0 : raw) : Math.round(raw)
        : null;
      const periodEnd = kind === '연' ? `${row.label}-12-31`
        : new Date(Date.UTC(Number(row.label.slice(0, 4)), Number(row.label.slice(5, 7)), 0)).toISOString().slice(0, 10);
      return { ...row, value, key: `${row.kind}/${row.label}`, ongoing: row.end < periodEnd,
        provisional: value !== null && metric === 'profit' && (row.warning || '').includes('외부 입출금 기록 확인') };
    });
}

export function performanceValue(value, metric, compact = false) {
  if (value === null) return '계산 대기';
  if (metric === 'return_pct') return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  if (!compact) return formatKRW(value, metric !== 'value_krw');
  const absolute = Math.abs(value);
  const sign = value < 0 ? '-' : value > 0 && metric !== 'value_krw' ? '+' : '';
  const unit = absolute >= 100000000 ? [100000000, '억 원'] : absolute >= 10000 ? [10000, '만 원'] : [1, '원'];
  return `${sign}${(absolute / unit[0]).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}${unit[1]}`;
}

export const performanceDay = label => Date.parse(`${label}T00:00:00Z`) / 86400000;

export function dailyPerformanceSeries(reports, metric, range = '90') {
  const ordered = [...reports].sort((a, b) => a.label.localeCompare(b.label));
  const lastDay = ordered.length ? performanceDay(ordered.at(-1).label) : 0;
  return ordered.filter(row => range === 'all' || performanceDay(row.label) >= lastDay - Number(range) + 1)
    .map(row => {
      const raw = row[metric];
      const value = typeof raw === 'number' && Number.isFinite(raw)
        ? metric === 'return_pct' ? (Math.abs(raw) < 0.005 ? 0 : raw) : Math.round(raw) : null;
      return { ...row, value, key: `일/${row.label}`, provisional: metric === 'profit' && value !== null &&
        (row.warning || '').includes('외부 입출금 기록 확인') };
    });
}

// Never connect across an unrecorded day or a pending calculation.
export function dailyPerformanceSegments(series) {
  return series.slice(1).flatMap((row, index) => {
    const previous = series[index];
    return previous.value !== null && row.value !== null && performanceDay(row.label) - performanceDay(previous.label) === 1
      ? [{ from: previous, to: row, provisional: previous.provisional || row.provisional }] : [];
  });
}

export function performanceDomain(series, metric) {
  if (metric !== 'value_krw') {
    const scale = performanceScale(series, metric);
    return [-scale, scale];
  }
  const values = series.filter(row => row.value !== null).map(row => row.value);
  if (!values.length) return [0, 100000];
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.1, maximum * 0.01, 1);
  return [Math.max(0, minimum - padding), maximum + padding];
}

export function performanceScale(series, metric) {
  const maximum = Math.max(0, ...series.map(row => Math.abs(row.value ?? 0)));
  if (!maximum) return metric === 'return_pct' ? 1 : 100000;
  const magnitude = 10 ** Math.floor(Math.log10(maximum));
  const fraction = maximum / magnitude;
  return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10) * magnitude;
}
