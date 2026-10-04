/** CryptoSummaryCards: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Sparkles } from 'lucide-react';
import { formatKRW, formatPercent } from '../../utils/formatters';

export default function CryptoSummaryCards({ cryptoTotal, isCryptoProfit, hongil, yoona }) {
  return (
    <>
      {/* 1. Standalone Crypto Portfolio Overview (가상화폐 전체 총계) */}
      <div className="section-card" style={{ background: 'linear-gradient(145deg, var(--bg-card), rgba(245, 158, 11, 0.04))', border: '1px solid rgba(245, 158, 11, 0.25)' }}>
        <div className="section-title" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#F59E0B', fontWeight: 800 }}>
            <Sparkles size={18} />
            🪙 가상화폐 자산 종합 총계 (업비트)
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            홍일 & 윤아 합산 총 평가액: {formatKRW(cryptoTotal.total_eval)}
          </span>
        </div>

        {/* 4 KPI Cards Grid */}
        <div className="kpi-grid" style={{ marginTop: '16px', marginBottom: '16px' }}>
          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">💎 가상화폐 총 평가금액</div>
            <div className="kpi-value" style={{ color: 'var(--accent-primary)', fontSize: '1.45rem' }}>
              {formatKRW(cryptoTotal.total_eval)}
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">🛒 가상화폐 총 매입금액 (원금)</div>
            <div className="kpi-value" style={{ fontSize: '1.45rem' }}>
              {formatKRW(cryptoTotal.total_buy)}
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">📈 가상화폐 총 평가손익 (수익률)</div>
            <div className="kpi-value" style={{ color: isCryptoProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontSize: '1.45rem' }}>
              {isCryptoProfit ? '+' : ''}{formatKRW(cryptoTotal.total_profit)}
              <span style={{ fontSize: '0.95rem', marginLeft: '6px', fontWeight: 600 }}>
                ({formatPercent(cryptoTotal.total_profit_pct)})
              </span>
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">⚖️ 홍일 vs 윤아 지분율 비중</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', fontWeight: 700 }}>
                <span style={{ color: '#0EA5E9' }}>👨 홍일 {hongil.share_pct?.toFixed(1)}%</span>
                <span style={{ color: '#EC4899' }}>👩 윤아 {yoona.share_pct?.toFixed(1)}%</span>
              </div>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                <div style={{ width: `${hongil.share_pct || 0}%`, background: '#0EA5E9' }} title={`홍일: ${hongil.share_pct?.toFixed(1)}%`} />
                <div style={{ width: `${yoona.share_pct || 0}%`, background: '#EC4899' }} title={`윤아: ${yoona.share_pct?.toFixed(1)}%`} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                <span>{formatKRW(hongil.total_eval)}</span>
                <span>{formatKRW(yoona.total_eval)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
