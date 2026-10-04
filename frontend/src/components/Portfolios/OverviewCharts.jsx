/** OverviewCharts: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { PieChart } from 'lucide-react';
import { formatKRW } from '../../utils/formatters';
import DonutChart from '../common/DonutChart';

export default function OverviewCharts({
  setChartView,
  chartView,
  portfolioDonutData,
  grand,
  assetClassDonutData,
}) {
  return (
    <>
      {/* 2. Interactive Donut Charts Section (포트폴리오별 / 자산군별 비중) */}
      <div className="section-card">
        <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PieChart size={18} color="var(--accent-primary)" />
            통합 자산 구성 비중 분석 (도넛 차트)
          </span>

          <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-surface)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('dual')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'dual' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'dual' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              포트폴리오 & 자산군 듀얼
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('portfolios')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'portfolios' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'portfolios' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              포트폴리오별 비중
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('assetClasses')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'assetClasses' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'assetClasses' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              자산군 대분류별 비중
            </button>
          </div>
        </div>

        {/* Charts Grid Container */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: chartView === 'dual' ? 'repeat(auto-fit, minmax(360px, 1fr))' : '1fr',
          gap: '24px',
          marginTop: '12px'
        }}>
          {(chartView === 'dual' || chartView === 'portfolios') && (
            <div style={{
              background: 'var(--bg-surface)',
              padding: '16px 20px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)'
            }}>
              <DonutChart
                title="💼 포트폴리오별 순자산 구성 비중"
                data={portfolioDonutData}
                centerLabel="전체 순자산"
                centerValue={formatKRW(grand.total_eval)}
                size={230}
              />
            </div>
          )}

          {(chartView === 'dual' || chartView === 'assetClasses') && (
            <div style={{
              background: 'var(--bg-surface)',
              padding: '16px 20px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)'
            }}>
              <DonutChart
                title="🌐 자산군 대분류별 자산 비중"
                data={assetClassDonutData}
                centerLabel="전체 순자산"
                centerValue={formatKRW(grand.total_eval)}
                size={230}
              />
            </div>
          )}
        </div>
      </div>
    </>
  );
}
