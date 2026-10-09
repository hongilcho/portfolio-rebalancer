/** DashboardCharts: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { PieChart } from 'lucide-react';
import { formatKRW } from '../../utils/formatters';
import {useCompactLayout} from '../../utils/useCompactLayout';
import DonutChart from '../common/DonutChart';

export default function DashboardCharts({
  setChartView,
  chartView,
  includeDeposits,
  stockDonutData,
  totalStockEval,
  assetTypeDonutData,
}) {
  const compact=useCompactLayout();
  if(compact)return <section className="section-card mobile-allocation-chart"><h3>자산군별 비중</h3>
    <DonutChart data={assetTypeDonutData} centerLabel={includeDeposits?'투자자산 평가액':'예금 제외 평가액'} centerValue={formatKRW(totalStockEval)} size={190}/>
    <details><summary>종목별 비중 상세보기</summary><DonutChart data={stockDonutData} centerLabel="투자자산 평가액" centerValue={formatKRW(totalStockEval)} size={190}/></details>
  </section>;
  return (
    <>
      {/* 2. Interactive Donut Charts Section (개별 종목별 / 종목 유형별 비중) */}
      <div className="section-card" style={{ marginBottom: '20px' }}>
        <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PieChart size={18} color="var(--accent-primary)" />
            포트폴리오 비중 분석 (도넛 차트)
          </span>

          <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-surface)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('both')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'both' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'both' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              종목 & 유형 듀얼
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('stocks')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'stocks' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'stocks' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              개별 종목별
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('types')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'types' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'types' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              종목 유형별
            </button>
          </div>
        </div>

        {/* Charts Container */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: chartView === 'both' ? 'repeat(auto-fit, minmax(min(100%, 360px), 1fr))' : '1fr',
          gap: '24px',
          marginTop: '12px'
        }}>
          {(chartView === 'both' || chartView === 'stocks') && (
            <div style={{
              background: 'var(--bg-surface)',
              padding: '16px 20px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)'
            }}>
              <DonutChart
                title={includeDeposits ? "📈 개별 종목별 자산 평가액 비중" : "📈 개별 종목별 자산 평가액 비중 (예금 제외)"}
                data={stockDonutData}
                centerLabel={includeDeposits ? "투자자산 총 평가액" : "투자자산 총 평가액 (예금 제외)"}
                centerValue={formatKRW(totalStockEval)}
                size={230}
              />
            </div>
          )}

          {(chartView === 'both' || chartView === 'types') && (
            <div style={{
              background: 'var(--bg-surface)',
              padding: '16px 20px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)'
            }}>
              <DonutChart
                title={includeDeposits ? "🏛️ 종목 유형별 자산 평가액 비중 (주식/채권/대체투자/예금)" : "🏛️ 종목 유형별 자산 평가액 비중 (주식/채권/대체투자)"}
                data={assetTypeDonutData}
                centerLabel={includeDeposits ? "투자자산 총 평가액" : "투자자산 총 평가액 (예금 제외)"}
                centerValue={formatKRW(totalStockEval)}
                size={230}
              />
            </div>
          )}
        </div>
      </div>
    </>
  );
}
