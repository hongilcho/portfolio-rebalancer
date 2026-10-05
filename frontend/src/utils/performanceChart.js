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
  if (!compact) return formatKRW(value, true);
  const absolute = Math.abs(value);
  const sign = value < 0 ? '-' : value > 0 ? '+' : '';
  const unit = absolute >= 100000000 ? [100000000, '억 원'] : absolute >= 10000 ? [10000, '만 원'] : [1, '원'];
  return `${sign}${(absolute / unit[0]).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}${unit[1]}`;
}

export function performanceScale(series, metric) {
  const maximum = Math.max(0, ...series.map(row => Math.abs(row.value ?? 0)));
  if (!maximum) return metric === 'return_pct' ? 1 : 100000;
  const magnitude = 10 ** Math.floor(Math.log10(maximum));
  const fraction = maximum / magnitude;
  return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10) * magnitude;
}
