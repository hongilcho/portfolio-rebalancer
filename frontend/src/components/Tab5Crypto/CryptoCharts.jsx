/** CryptoCharts: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { PieChart } from 'lucide-react';
import { formatKRW } from '../../utils/formatters';
import DonutChart from '../common/DonutChart';

export default function CryptoCharts({
  setChartView,
  chartView,
  ownerDonutData,
  cryptoTotal,
  coinDonutData,
}) {
  return (
    <>
      {/* 2. Interactive Donut Charts Section (지분율 / 코인별 비중) */}
      <div className="section-card">
        <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PieChart size={18} color="#F59E0B" />
            가상화폐 비중 분석 (도넛 차트)
          </span>

          <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-surface)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('both')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'both' ? '#F59E0B' : 'transparent',
                color: chartView === 'both' ? '#000' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              지분 & 코인 듀얼
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('owner')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'owner' ? '#F59E0B' : 'transparent',
                color: chartView === 'owner' ? '#000' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              홍일 vs 윤아 지분
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('coin')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'coin' ? '#F59E0B' : 'transparent',
                color: chartView === 'coin' ? '#000' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              코인별 비중 (BTC/ETH)
            </button>
          </div>
        </div>

        {/* Charts Container */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: chartView === 'both' ? 'repeat(auto-fit, minmax(360px, 1fr))' : '1fr',
          gap: '24px',
          marginTop: '12px'
        }}>
          {(chartView === 'both' || chartView === 'owner') && (
            <div style={{
              background: 'var(--bg-surface)',
              padding: '16px 20px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)'
            }}>
              <DonutChart
                title="👥 홍일 vs 윤아 지분 비중"
                data={ownerDonutData}
                centerLabel="가상화폐 총 평가액"
                centerValue={formatKRW(cryptoTotal.total_eval)}
                size={230}
              />
            </div>
          )}

          {(chartView === 'both' || chartView === 'coin') && (
            <div style={{
              background: 'var(--bg-surface)',
              padding: '16px 20px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)'
            }}>
              <DonutChart
                title="🪙 비트코인 vs 이더리움 비중"
                data={coinDonutData}
                centerLabel="코인 총 평가액"
                centerValue={formatKRW(cryptoTotal.total_eval)}
                size={230}
              />
            </div>
          )}
        </div>
      </div>
    </>
  );
}
