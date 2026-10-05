import React, { useEffect, useRef, useState } from 'react';
import { performanceSeries, performanceValue, performanceScale } from '../../utils/performanceChart';

export default function PerformanceChart({ reports }) {
  const [kind, setKind] = useState('월');
  const [metric, setMetric] = useState('return_pct');
  const [year, setYear] = useState('latest');
  const [selectedKey, setSelectedKey] = useState(null);
  const [containerWidth, setContainerWidth] = useState(560);
  const chartRef = useRef(null);
  const years = [...new Set(reports.filter(row => row.kind === '월').map(row => row.label.slice(0, 4)))].sort();
  const selectedYear = years.includes(year) ? year : years.at(-1);
  const series = performanceSeries(reports, kind, metric, selectedYear);
  const selected = series.find(row => row.key === selectedKey) || series.at(-1);
  const scale = performanceScale(series, metric);
  const hasSeries = series.length > 0;
  useEffect(() => {
    if (!chartRef.current) return;
    const observer = new ResizeObserver(entries => setContainerWidth(Math.floor(entries[0].contentRect.width)));
    observer.observe(chartRef.current);
    return () => observer.disconnect();
  }, [hasSeries]);
  const width = Math.max(containerWidth, 560, 110 + series.length * 100);
  const left = 90, right = width - 20, top = 36, bottom = 244, zero = (top + bottom) / 2;
  const y = value => zero - value / scale * (bottom - top) / 2;
  const slot = (right - left) / Math.max(1, series.length);
  const selectedIndex = series.findIndex(row => row.key === selected?.key);
  useEffect(() => {
    if (chartRef.current && selectedIndex >= 0) {
      // Keep the latest/selected period visible on a phone without scrolling
      // the whole page. Manual panning remains available between selections.
      chartRef.current.scrollLeft = left + slot * (selectedIndex + 0.5) - chartRef.current.clientWidth / 2;
    }
  }, [width, slot, selectedIndex]);
  const chooseKind = value => { setKind(value); setSelectedKey(null); };
  const chooseMetric = value => setMetric(value);
  const metricLabel = metric === 'return_pct' ? '금액가중 기간 수익률' : '기간 손익';

  return <section className="performance-chart" aria-label="기간 성과 그래프">
    <h3>기간 성과 그래프</h3>
    <div className="performance-chart-controls">
      <div role="group" aria-label="성과 그래프 기간">
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={kind === '월'} onClick={() => chooseKind('월')}>월별</button>
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={kind === '연'} onClick={() => chooseKind('연')}>연간</button>
      </div>
      <div role="group" aria-label="성과 그래프 지표">
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={metric === 'return_pct'} onClick={() => chooseMetric('return_pct')}>수익률 (%)</button>
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={metric === 'profit'} onClick={() => chooseMetric('profit')}>손익 (원)</button>
      </div>
      {kind === '월' && years.length > 0 && <label>연도 <select aria-label="성과 그래프 연도" className="input-select" value={selectedYear}
        onChange={event => { setYear(event.target.value); setSelectedKey(null); }}>{years.map(item => <option key={item} value={item}>{item}년</option>)}</select></label>}
    </div>
    <p>{metricLabel} · 양수는 위쪽, 음수는 아래쪽으로 표시합니다. 막대를 누르거나 키보드로 선택하면 아래에서 상세 값을 확인할 수 있습니다.</p>
    {!series.length ? <p>표시할 기간 성과 기록이 없습니다. 시작 기준 등록 이후의 평가 기록을 확인해주세요.</p> : <>
      <div ref={chartRef} className="performance-chart-scroll" role="region" aria-label="기간 성과 막대그래프, 좁은 화면에서는 좌우로 이동" tabIndex={0}>
        <svg viewBox={`0 0 ${width} 340`} style={{ minWidth: width }} role="group" aria-label={`${kind === '월' ? `${selectedYear}년 월별` : '연간'} ${metricLabel} 그래프`}>
          {[-1, -0.5, 0, 0.5, 1].map(factor => <g key={factor}>
            <line x1={left} x2={right} y1={y(factor * scale)} y2={y(factor * scale)} stroke="var(--border-color)" strokeWidth={factor === 0 ? 2 : 1} />
            <text x={left - 10} y={y(factor * scale) + 4} textAnchor="end" fill="var(--text-secondary)" fontSize="11">{performanceValue(factor * scale, metric, true)}</text>
          </g>)}
          {series.map((row, index) => {
            const x = left + slot * (index + 0.5);
            const color = row.value > 0 ? 'var(--color-profit)' : row.value < 0 ? 'var(--color-loss)' : 'var(--text-secondary)';
            const label = `${row.label} ${performanceValue(row.value, metric)}${row.provisional ? ' (입출금 확인 전 잠정치)' : ''}${row.warning ? ` · ${row.warning}` : ''}`;
            return <g key={row.key} role="button" tabIndex={0} aria-label={label} aria-pressed={selected?.key === row.key}
              className="performance-chart-period" onClick={() => setSelectedKey(row.key)} onFocus={() => setSelectedKey(row.key)}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedKey(row.key); } }}>
              <title>{label}</title>
              <rect x={x - slot / 2 + 4} y={top - 20} width={slot - 8} height={bottom - top + 108} rx="8"
                fill={selected?.key === row.key ? 'var(--bg-surface)' : 'transparent'} stroke={selected?.key === row.key ? 'var(--accent-primary)' : 'transparent'} />
              {row.value === null ? <text x={x} y={zero - 10} textAnchor="middle" fill="var(--text-secondary)" fontSize="12">계산 대기</text>
                : row.value === 0 ? <line x1={x - 18} x2={x + 18} y1={zero} y2={zero} stroke={color} strokeWidth="3" />
                : <rect x={x - Math.min(40, slot * 0.4) / 2} y={Math.min(y(row.value), zero)} width={Math.min(40, slot * 0.4)} height={Math.abs(y(row.value) - zero)}
                  fill={color} fillOpacity={row.provisional ? 0.35 : 0.85} stroke={color} strokeDasharray={row.provisional ? '4 3' : undefined} rx="3" />}
              {row.value !== null && <text x={x} y={row.value >= 0 ? y(row.value) - 9 : y(row.value) + 17} textAnchor="middle" fill={color} fontSize="11">{performanceValue(row.value, metric, true)}</text>}
              <text x={x} y={bottom + 40} textAnchor="middle" fill="var(--text-primary)" fontSize="12">{row.label}</text>
              <text x={x} y={bottom + 57} textAnchor="middle" fill="var(--text-secondary)" fontSize="10">{row.ongoing ? `${row.end.slice(5).replace('-', '/')}까지` : row.partial ? '시작 기준 이후' : ''}</text>
              {row.provisional && <text x={x} y={bottom + 73} textAnchor="middle" fill="var(--text-secondary)" fontSize="10">잠정치</text>}
            </g>;
          })}
        </svg>
      </div>
      {selected && <div className="performance-chart-detail" aria-live="polite">
        <strong>{selected.label} · {metricLabel} {performanceValue(selected.value, metric)}{selected.provisional && ' (입출금 확인 전 잠정치)'}</strong>
        <p>{selected.start} ~ {selected.end}{selected.partial && ' · 시작 기준 등록 이후'}{selected.ongoing && ' · 최근 평가일까지'}</p>
        {selected.warning && <p>{selected.warning}</p>}
      </div>}
      <p className="performance-chart-note">계산 대기는 0%·0원으로 표시하지 않습니다. 진행 중인 기간은 최근 평가일까지 표시하며, 정확한 금액과 계산 상태는 아래 표에서 확인할 수 있습니다.</p>
      {series.some(row => row.provisional) && <p>점선 막대는 입출금 확인 전의 잠정 손익입니다. 입출금 기록을 확인하면 잠정치 표시를 해제합니다.</p>}
    </>}
  </section>;
}
