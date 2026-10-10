import React from 'react';
import { sortInvestmentAssets } from '../../utils/assetClasses';

const percent = value => value != null && Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}%` : '—';

export default function WeightDriftOverview({ items = [], scaleMax }) {
  const rows = sortInvestmentAssets(items);
  const scale = Math.max(1, Number(scaleMax) || 0,
    ...rows.map(item => Math.abs(Number(item.drift_pct)) || 0));

  return (
    <section className="section-card weight-drift-overview" aria-label="목표 대비 비중 차이">
      <div className="weight-drift-heading">
        <h3>목표 대비 비중 차이</h3>
        <span className="weight-drift-unit">%p</span>
      </div>
      <div className="weight-drift-legend" aria-hidden="true">
        <span>← 목표 미달</span><span>목표 초과 →</span>
      </div>
      {rows.length === 0 ? <p className="weight-drift-empty">비중 비교 대상 종목이 없습니다.</p> : (
        <ul className="weight-drift-list">
          {rows.map(item => {
            const drift = Number(item.drift_pct);
            const known = item.drift_pct != null && Number.isFinite(drift);
            const rounded = known ? Number(drift.toFixed(1)) : 0;
            const direction = !known ? 'unknown' : rounded > 0 ? 'over' : rounded < 0 ? 'under' : 'balanced';
            const difference = !known ? '비중 확인 필요' : rounded > 0 ? `초과 +${rounded.toFixed(1)}%p` : rounded < 0 ? `미달 −${Math.abs(rounded).toFixed(1)}%p` : '차이 0.0%p';
            return <li key={item.asset_id} className={`weight-drift-row is-${direction}`}>
              <div className="weight-drift-row-heading">
                <span className="weight-drift-name">{item.name}</span>
                <strong className="weight-drift-difference">{difference}</strong>
              </div>
              <div className="weight-drift-row-chart">
                <span className="weight-drift-weights">현재 <b>{percent(item.weight_pct)}</b> · 목표 {percent(item.target_weight_pct)}</span>
                <div className="weight-drift-track" aria-hidden="true">
                  <span className="weight-drift-center" />
                  {known && rounded !== 0 && <span className="weight-drift-fill" style={{
                    width: `${Math.min(50, Math.abs(drift) / scale * 50)}%`,
                    ...(drift > 0 ? { left: '50%' } : { right: '50%' }),
                  }} />}
                  {known && rounded === 0 && <span className="weight-drift-dot" />}
                </div>
              </div>
            </li>;
          })}
        </ul>
      )}
      {rows.length > 0 && <div className="weight-drift-scale" aria-hidden="true"><span>−{scale.toFixed(1)}%p</span><span>0</span><span>+{scale.toFixed(1)}%p</span></div>}
    </section>
  );
}
