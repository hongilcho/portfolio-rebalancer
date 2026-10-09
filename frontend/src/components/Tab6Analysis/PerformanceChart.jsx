import React, { useEffect, useRef, useState } from 'react';
import { performanceSeries, performanceValue, performanceAxisValue, performanceDomain, performanceDay,
  dailyPerformanceSeries, dailyPerformanceSegments,performanceChartLayout,nearestPerformanceRecord } from '../../utils/performanceChart';

export default function PerformanceChart({ reports = [], dailyReports = [], baselineDate }) {
  const [kind, setKind] = useState(dailyReports.length ? '일' : '월');
  const [metric, setMetric] = useState('return_pct');
  const [year, setYear] = useState('latest');
  const [range, setRange] = useState('auto');
  const [selectedKey, setSelectedKey] = useState(null);
  const [containerWidth, setContainerWidth] = useState(560);
  const {width,compact,left,right,top,bottom,height}=performanceChartLayout(containerWidth);
  const effectiveRange=range==='auto'?(compact?'30':'90'):range;
  const chartRef = useRef(null);
  const years = [...new Set(reports.filter(row => row.kind === '월').map(row => row.label.slice(0, 4)))].sort();
  const selectedYear = years.includes(year) ? year : years.at(-1);
  const daily = kind === '일';
  const series = daily ? dailyPerformanceSeries(dailyReports, metric, effectiveRange) : performanceSeries(reports, kind, metric, selectedYear);
  const selected = series.find(row => row.key === selectedKey) || series.at(-1);
  const [minimum, maximum] = performanceDomain(series, metric);
  const hasSeries = series.length > 0;
  useEffect(() => {
    if (!chartRef.current) return;
    const observer = new ResizeObserver(entries => setContainerWidth(Math.floor(entries[0].contentRect.width)));
    observer.observe(chartRef.current);
    return () => observer.disconnect();
  }, [hasSeries]);
  const firstDay = series.length ? performanceDay(series[0].label) : 0;
  const daySpan = daily && series.length ? performanceDay(series.at(-1).label) - firstDay : 0;
  const y = value => bottom - (value - minimum) / (maximum - minimum) * (bottom - top);
  const zero = y(0);
  const slot = (right - left) / Math.max(1, series.length);
  const dailyX = row => daySpan ? left + (performanceDay(row.label) - firstDay) / daySpan * (right - left) : (left + right) / 2;
  const selectedIndex = series.findIndex(row => row.key === selected?.key);
  const selectedX = daily && selected ? dailyX(selected) : left + slot * (selectedIndex + 0.5);
  const navigateRecord = row => { if(row)setSelectedKey(row.key); };
  const selectAtPointer=event=>{
    if(!event.detail)return;
    const rect=event.currentTarget.getBoundingClientRect();
    const x=(event.clientX-rect.left)/rect.width*width;
    navigateRecord(nearestPerformanceRecord(series,x,left,right,daily));
  };
  const chooseKind = value => { setKind(value); setSelectedKey(null); if (value !== '일' && metric === 'value_krw') setMetric('return_pct'); };
  const chooseMetric = value => setMetric(value);
  const metricLabel = metric === 'value_krw' ? '평가액' : metric === 'return_pct'
    ? daily ? '기준일부터 누적 금액가중 수익률' : '금액가중 기간 수익률' : daily ? '기준일부터 누적 손익' : '기간 손익';
  const tooltipWidth=Math.min(210,right-left);
  const tooltipX=Math.max(left,Math.min(right-tooltipWidth,selectedX-tooltipWidth/2));
  const segments = daily ? dailyPerformanceSegments(series) : [];
  const ticks = [];
  if (daily && series.length) {
    ticks.push(series[0]);
    for (const row of series.slice(1, -1)) {
      if (dailyX(row) - dailyX(ticks.at(-1)) >= 80 && dailyX(series.at(-1)) - dailyX(row) >= 80) ticks.push(row);
    }
    if (series.length > 1) ticks.push(series.at(-1));
  }

  return <section className="performance-chart" aria-label="기간 성과 그래프">
    <h3>기간 성과 그래프</h3>
    <div className="performance-chart-controls">
      <div role="group" aria-label="성과 그래프 기간">
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={daily} onClick={() => chooseKind('일')}>일별 추이</button>
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={kind === '월'} onClick={() => chooseKind('월')}>월별</button>
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={kind === '연'} onClick={() => chooseKind('연')}>연간</button>
      </div>
      <div role="group" aria-label="성과 그래프 지표">
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={metric === 'return_pct'} onClick={() => chooseMetric('return_pct')}>수익률 (%)</button>
        <button type="button" className="btn btn-secondary btn-sm" aria-pressed={metric === 'profit'} onClick={() => chooseMetric('profit')}>손익 (원)</button>
        {daily && <button type="button" className="btn btn-secondary btn-sm" aria-pressed={metric === 'value_krw'} onClick={() => chooseMetric('value_krw')}>평가액 (원)</button>}
      </div>
      {kind === '월' && years.length > 0 && <label>연도 <select aria-label="성과 그래프 연도" className="input-select" value={selectedYear}
        onChange={event => { setYear(event.target.value); setSelectedKey(null); }}>{years.map(item => <option key={item} value={item}>{item}년</option>)}</select></label>}
      {daily && <label>표시 범위 <select aria-label="일별 그래프 표시 범위" className="input-select" value={range}
        onChange={event => { setRange(event.target.value); setSelectedKey(null); }}>
        <option value="auto">기본 · 최근 {compact?30:90}일</option><option value="30">최근 기록일 기준 30일</option><option value="90">최근 기록일 기준 90일</option>
        <option value="365">최근 기록일 기준 1년</option><option value="all">전체 기록</option>
      </select></label>}
    </div>
    <p className="performance-chart-caption">{compact?(metric==='value_krw'?'평가액':daily?metric==='return_pct'?'기준일부터 누적 수익률':'기준일부터 누적 손익':metricLabel):metricLabel}
      {daily && baselineDate && <small className="performance-chart-baseline">기준일 <time dateTime={baselineDate}>{baselineDate}</time></small>}
    </p>
    {!series.length ? <p>표시할 기간 성과 기록이 없습니다. 시작 기준 등록 이후의 평가 기록을 확인해주세요.</p> : <>
      {selected && <p className="performance-chart-value" aria-live="polite" aria-atomic="true">
        <strong>{selected.label} · {performanceValue(selected.value, metric)}</strong>
      </p>}
      <div ref={chartRef} className="performance-chart-scroll" role="region" aria-label={`기간 성과 ${daily ? '연결선' : '막대'}그래프, 선택 기간 전체 표시`} tabIndex={0}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{height}} onClick={selectAtPointer} role="group" aria-label={`${daily ? '일별 누적' : kind === '월' ? `${selectedYear}년 월별` : '연간'} ${metricLabel} 그래프`}>
          {(compact?[0,0.5,1]:[0,0.25,0.5,0.75,1]).map(factor=><text key={`axis-${factor}`} x={left-8} y={y(minimum+factor*(maximum-minimum))+4} textAnchor="end" fill="var(--text-secondary)" fontSize={compact?10:11}>{performanceAxisValue(minimum+factor*(maximum-minimum),metric,maximum-minimum).replaceAll(' ','')}</text>)}
          <rect x={left} y={top} width={right-left} height={bottom-top} fill="transparent"/>
          {(compact?[0,0.5,1]:[0,0.25,0.5,0.75,1]).map(factor => <g key={factor}>
            <line x1={left} x2={right} y1={y(minimum + factor * (maximum - minimum))} y2={y(minimum + factor * (maximum - minimum))} stroke="var(--border-color)" strokeWidth={factor === 0.5 && metric !== 'value_krw' ? 2 : 1} />
          </g>)}
          {daily ? <>
            {selected && <line x1={selectedX} x2={selectedX} y1={top} y2={bottom} stroke="var(--accent-primary)" strokeDasharray="3 3" />}
            {segments.map(segment => <line key={segment.to.key} x1={dailyX(segment.from)} x2={dailyX(segment.to)}
              y1={y(segment.from.value)} y2={y(segment.to.value)} stroke="var(--accent-primary)" strokeWidth="2.5" />)}
            {series.map((row, index) => {
              const x = dailyX(row), pointY = row.value === null ? top : y(row.value);
              const label = `${row.label} ${metricLabel} ${performanceValue(row.value, metric)}`;
              return <g key={row.key} role="button" tabIndex={0} aria-label={label} aria-pressed={selected?.key === row.key}
                className="performance-chart-point" onClick={() => setSelectedKey(row.key)} onFocus={() => setSelectedKey(row.key)}
                onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedKey(row.key); }
                  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                    event.preventDefault();
                    const target = series[Math.max(0, Math.min(series.length - 1, index + (event.key === 'ArrowLeft' ? -1 : 1)))];
                    navigateRecord(target);
                    const siblings = event.currentTarget.parentElement.querySelectorAll('.performance-chart-point');
                    siblings[series.indexOf(target)]?.focus();
                  }
                }}>
                <title>{`${label}${row.warning ? ` · ${row.warning}` : ''}`}</title>
                {!compact && <circle cx={x} cy={pointY} r="22" fill="transparent" pointerEvents="all" />}
                {row.value === null ? <text x={x} y={pointY + 4} textAnchor="middle" fill="var(--text-secondary)" fontSize="12">×</text>
                  : (!compact || series.length<=12 || selected?.key===row.key || index===0 || index===series.length-1) && <circle cx={x} cy={pointY} r={selected?.key === row.key ? 6 : 4} fill="var(--accent-primary)" stroke="var(--accent-primary)" strokeWidth="2" />}
              </g>;
            })}
            {ticks.map(row => <text key={row.key} x={dailyX(row)} y={bottom + 35}
              textAnchor={row === series[0] ? 'start' : row === series.at(-1) ? 'end' : 'middle'}
              fill="var(--text-secondary)" fontSize="11">{(compact?row.label.slice(5):row.label.slice(2)).replaceAll('-', '/')}</text>)}
            {!compact && selectedKey && selected && <g className="performance-chart-tooltip" pointerEvents="none"
              transform={`translate(${tooltipX},${Math.max(8, (selected.value === null ? top : y(selected.value)) - 66)})`}>
              <rect width={tooltipWidth} height="54" rx="8" fill="var(--bg-surface)" stroke="var(--accent-primary)" />
              <text x={tooltipWidth / 2} y="20" textAnchor="middle" fill="var(--text-secondary)" fontSize="12">{selected.label}</text>
              <text x={tooltipWidth / 2} y="40" textAnchor="middle" fill="var(--text-primary)" fontSize="14" fontWeight="700">{performanceValue(selected.value, metric)}</text>
            </g>}
          </> : series.map((row, index) => {
            const x = left + slot * (index + 0.5);
            const color = row.value > 0 ? 'var(--color-profit)' : row.value < 0 ? 'var(--color-loss)' : 'var(--text-secondary)';
            const label = `${row.label} ${performanceValue(row.value, metric)}${row.warning ? ` · ${row.warning}` : ''}`;
            return <g key={row.key} role="button" tabIndex={0} aria-label={label} aria-pressed={selected?.key === row.key}
              className="performance-chart-period" onClick={() => setSelectedKey(row.key)} onFocus={() => setSelectedKey(row.key)}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedKey(row.key); } }}>
              <title>{label}</title>
              <rect x={x - slot / 2 + 4} y={top - 20} width={Math.max(1,slot - 8)} height={bottom - top + 108} rx="8"
                fill={selected?.key === row.key ? 'var(--bg-surface)' : 'transparent'} stroke={selected?.key === row.key ? 'var(--accent-primary)' : 'transparent'} />
              {row.value === null ? <text x={x} y={zero - 10} textAnchor="middle" fill="var(--text-secondary)" fontSize="12">계산 대기</text>
                : row.value === 0 ? <line x1={x - 18} x2={x + 18} y1={zero} y2={zero} stroke={color} strokeWidth="3" />
                : <rect x={x - Math.min(40, slot * 0.4) / 2} y={Math.min(y(row.value), zero)} width={Math.min(40, slot * 0.4)} height={Math.abs(y(row.value) - zero)}
                  fill={color} fillOpacity={0.85} stroke={color} rx="3" />}
              {!compact && row.value !== null && <text x={x} y={row.value >= 0 ? y(row.value) - 9 : y(row.value) + 17} textAnchor="middle" fill={color} fontSize="11">{performanceValue(row.value, metric, true)}</text>}
              {(!compact || index%Math.max(1,Math.ceil(series.length/4))===0 || index===series.length-1) && <text x={x} y={bottom + 35} textAnchor="middle" fill="var(--text-primary)" fontSize={compact?10:12}>{compact && kind==='월'?`${row.label.slice(5)}월`:row.label}</text>}
              {!compact && <text x={x} y={bottom + 57} textAnchor="middle" fill="var(--text-secondary)" fontSize="10">{row.ongoing ? `${row.end.slice(5).replace('-', '/')}까지` : row.partial ? '시작 기준 이후' : ''}</text>}
            </g>;
          })}
        </svg>
      </div>
      {selected && <div className="performance-chart-detail">
        {daily && <div className="performance-chart-controls" role="group" aria-label="일별 기록 선택">
          <button type="button" className="btn btn-secondary btn-sm" disabled={selectedIndex <= 0}
            onClick={() => navigateRecord(series[selectedIndex - 1])}>이전 기록</button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={selectedIndex >= series.length - 1}
            onClick={() => navigateRecord(series[selectedIndex + 1])}>다음 기록</button>
        </div>}
        {selected.flow_count>0 && <p>외부 입출금 {selected.flow_count}건 반영</p>}
        <details><summary>선택한 기록 상세</summary>
        <p>{selected.start} ~ {selected.end}{selected.partial && ' · 시작 기준 등록 이후'}{selected.ongoing && ' · 최근 평가일까지'}</p>
        {daily && <p>평가액 {performanceValue(selected.value_krw, 'value_krw')} · 누적 순입금 {performanceValue(selected.net_flow, 'profit')} · 누적 손익 {performanceValue(selected.profit, 'profit')}</p>}
        {daily && selected.recorded_at && <p>마지막 기록 시각 {new Date(selected.recorded_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} (한국 시간)</p>}
        {daily && <p>평가 기준 {selected.record_kind === 'close' ? '정규장 종가' : selected.record_kind === 'baseline' ? selected.baseline_kind === 'closing_baseline' ? '종가 기준 시작 평가액' : '시작 기준 등록 시점' : '이전 조회 시점 기록'}</p>}
        {daily && selected.fx && <p>적용 환율 {Number(selected.fx.rate).toLocaleString('ko-KR')} 원/USD{selected.fx.published_at
          ? ` · 고시 ${new Date(selected.fx.published_at).toLocaleString('ko-KR', {timeZone:'Asia/Seoul'})}`
          : selected.fx.collected_at ? ` · 저장 ${new Date(selected.fx.collected_at).toLocaleString('ko-KR', {timeZone:'Asia/Seoul'})}` : ''}</p>}
        {daily && selected.ledger_at && <p>장부 수집 시각 {new Date(selected.ledger_at).toLocaleString('ko-KR', {timeZone:'Asia/Seoul'})} (한국 시간)</p>}
        {daily && selected.closes?.length>0 && <details><summary>종가 날짜·출처 확인</summary>{selected.closes.map(c=><p key={c.id}>{c.ticker || '예금'} · {c.price_date} · {c.source}</p>)}</details>}
        </details>
        {selected.warning && <p role="status">{selected.warning}</p>}
        {selected.ongoing && <p className="history-muted">진행 중인 기간 · 최근 평가일까지의 성과입니다.</p>}
      </div>}
      <details><summary>그래프 보는 법</summary>
      <p>{daily ? '점을 선택하면 해당 날짜의 값을 확인할 수 있습니다. 수익률·손익은 시작 기준일부터의 누적 성과입니다. 표시 범위를 바꿔도 계산 기준일은 바뀌지 않습니다.' : '양수는 위쪽, 음수는 아래쪽으로 표시합니다. 막대를 선택하면 해당 기간의 상세 값을 확인할 수 있습니다.'}</p>
      <p className="performance-chart-note">{daily ? '종가 기록은 연속된 거래일 사이에 선을 연결합니다. 주말·휴장일은 건너뛰고, 누락된 거래일과 계산 대기 구간은 연결하지 않습니다. 하루만 기록되면 점 하나가 표시됩니다. 평가액은 입출금으로도 변하므로 수익률과 다릅니다. 기존 조회 기록은 날짜별 상세의 평가 기준으로 구분합니다.' : '계산 대기는 0%·0원으로 표시하지 않습니다. 진행 중인 기간은 최근 평가일까지 표시하며, 정확한 금액과 계산 상태는 아래 표에서 확인할 수 있습니다.'}</p>
      {daily && !series.some(row => row.value !== null) && <p>계산 대기 사유는 기록 상세에서 확인할 수 있습니다. 시작일 평가액이 변경된 경우 다음 날짜의 기록부터 수익률을 계산할 수 있습니다.</p>}
      <p>외부 입출금 기록이 없으면 입출금 없음으로 계산합니다. 실제 입출금이 있을 때만 5번 탭에 기록하면 날짜·금액이 자동 반영됩니다.</p>
      </details>
    </>}
  </section>;
}
