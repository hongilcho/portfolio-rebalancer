/** OverviewSummaryCards: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Layers } from 'lucide-react';
import { formatKRW, formatUSD, formatPercent, getProfitColor } from '../../utils/formatters';

export default function OverviewSummaryCards({
  portfolios,
  includeCrypto,
  crypto,
  currencyMode,
  grand,
  portfolioColors,
}) {
  return (
    <>
      {/* 1. Grand Total KPI Grid */}
      <div className="section-card" style={{ background: 'linear-gradient(145deg, var(--bg-card), rgba(99, 102, 241, 0.05))', border: '1px solid rgba(99, 102, 241, 0.25)' }}>
        <div className="section-title" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-primary)', fontWeight: 800 }}>
            <Layers size={18} />
            🌟 가문 전체 통합 자산 요약
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            (포트폴리오 {portfolios.length}개{includeCrypto && crypto ? ' + 가상화폐' : ''})
          </span>
        </div>

        {currencyMode === 'USD' ? (
          <div style={{ marginTop: '16px', marginBottom: '16px' }}>
            <div className="dual-currency-kpi-grid">
              {/* 1) 🇺🇸 가문 외화 자산 종합 (USD) */}
              <div className="dual-kpi-card usd-card">
                <div className="dual-kpi-header">
                  <div className="dual-kpi-title">
                    <span className="badge badge-accent">🇺🇸 가문 외화 자산 종합 (USD)</span>
                    <span className="dual-kpi-subtitle">미국 상장 ETF/주식 & 외화 예수금 통합</span>
                  </div>
                  <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: 'var(--accent-primary)', fontSize: '0.74rem' }}>
                    외화 순자산 {formatUSD(grand?.usd_summary?.total_eval_usd)}
                  </span>
                </div>
                <div className="dual-kpi-main">
                  <div className="dual-kpi-main-label">외화 총 평가금액</div>
                  <div className="dual-kpi-main-value" style={{ color: 'var(--accent-primary)' }}>
                    {formatUSD(grand?.usd_summary?.stock_eval_usd)}
                  </div>
                  <div className="dual-kpi-sub-row">
                    <span className="dual-kpi-sub-label">외화 배당 포함 손익:</span>
                    <span className="dual-kpi-sub-value" style={{ color: getProfitColor(grand?.usd_summary?.stock_profit_usd) }}>
                      {formatUSD(grand?.usd_summary?.stock_profit_usd, true)} ({formatPercent(grand?.usd_summary?.stock_return_usd)})
                    </span>
                  </div>
                  {(grand?.usd_summary?.stock_buy_usd || 0) > 0 && (
                    <div className="dual-kpi-sub-row" style={{ marginTop: '4px', fontSize: '0.78rem' }}>
                      <span className="dual-kpi-sub-label">💱 환차익(원화):</span>
                      <span className="dual-kpi-sub-value" style={{ color: getProfitColor(grand?.usd_summary?.total_fx_profit_krw) }}>
                        {formatKRW(grand?.usd_summary?.total_fx_profit_krw, true)} ({formatPercent(grand?.usd_summary?.total_fx_profit_pct)})
                      </span>
                    </div>
                  )}
                </div>
                <div className="dual-kpi-footer">
                  <div className="dual-kpi-footer-item">
                    <span>외화 투자원금</span>
                    <strong>{formatUSD(grand?.usd_summary?.stock_buy_usd)}</strong>
                    {(grand?.usd_summary?.weighted_buy_fx_rate || 0) > 0 && (
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                        @ {formatKRW(grand?.usd_summary?.weighted_buy_fx_rate)}/$
                      </span>
                    )}
                  </div>
                  <div className="dual-kpi-footer-divider" />
                  <div className="dual-kpi-footer-item">
                    <span>외화 예수금</span>
                    <strong style={{ color: 'var(--accent-primary)' }}>{formatUSD(grand?.usd_summary?.cash_usd)}</strong>
                  </div>
                </div>
              </div>

              {/* 2) 🇰🇷 가문 원화 자산 종합 (KRW) */}
              <div className="dual-kpi-card krw-card">
                <div className="dual-kpi-header">
                  <div className="dual-kpi-title">
                    <span className="badge badge-safe">🇰🇷 가문 원화 자산 종합 (KRW)</span>
                    <span className="dual-kpi-subtitle">국내 증시·채권·금·예금·가상화폐 & 원화 예수금</span>
                  </div>
                  <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-safe)', fontSize: '0.74rem' }}>
                    원화 순자산 {formatKRW(grand?.krw_summary?.total_eval_krw)}
                  </span>
                </div>
                <div className="dual-kpi-main">
                  <div className="dual-kpi-main-label">원화 총 평가금액</div>
                  <div className="dual-kpi-main-value" style={{ color: 'var(--color-safe)' }}>
                    {formatKRW(grand?.krw_summary?.stock_eval_krw)}
                  </div>
                  <div className="dual-kpi-sub-row">
                    <span className="dual-kpi-sub-label">원화 배당 포함 손익:</span>
                    <span className="dual-kpi-sub-value" style={{ color: getProfitColor(grand?.krw_summary?.stock_profit_krw) }}>
                      {formatKRW(grand?.krw_summary?.stock_profit_krw, true)} ({formatPercent(grand?.krw_summary?.stock_return_krw)})
                    </span>
                  </div>
                </div>
                <div className="dual-kpi-footer">
                  <div className="dual-kpi-footer-item">
                    <span>원화 투자원금</span>
                    <strong>{formatKRW(grand?.krw_summary?.stock_buy_krw)}</strong>
                  </div>
                  <div className="dual-kpi-footer-divider" />
                  <div className="dual-kpi-footer-item">
                    <span>원화 예수금</span>
                    <strong style={{ color: 'var(--color-safe)' }}>{formatKRW(grand?.krw_summary?.cash_krw)}</strong>
                  </div>
                </div>
              </div>
            </div>

            {/* Asset Distribution Bar */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px 16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', marginTop: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>⚖️ 자산 배분 비중 현황</span>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>통합 전체 환산 순자산: {formatKRW(grand.total_eval)}</span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '0.8rem', fontWeight: 700, marginBottom: '6px' }}>
                {portfolios.map((p, idx) => (
                  <span key={p.id} style={{ color: portfolioColors[idx % portfolioColors.length] }}>
                    💼 {p.name} {p.weight_pct?.toFixed(1)}%
                  </span>
                ))}
                {includeCrypto && crypto && (
                  <span style={{ color: '#F59E0B' }}>
                    🪙 가상화폐 {crypto.weight_pct?.toFixed(1)}%
                  </span>
                )}
              </div>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                {portfolios.map((p, idx) => (
                  <div
                    key={p.id}
                    style={{ width: `${p.weight_pct || 0}%`, background: portfolioColors[idx % portfolioColors.length] }}
                    title={`${p.name}: ${p.weight_pct?.toFixed(1)}%`}
                  />
                ))}
                {includeCrypto && crypto && (
                  <div
                    style={{ width: `${crypto.weight_pct || 0}%`, background: '#F59E0B' }}
                    title={`가상화폐: ${crypto.weight_pct?.toFixed(1)}%`}
                  />
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="kpi-grid" style={{ marginTop: '16px', marginBottom: '16px' }}>
            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">💎 통합 총 평가금액 (전체 순자산)</div>
              <div className="kpi-value" style={{ color: 'var(--accent-primary)', fontSize: '1.5rem' }}>
                {formatKRW(grand.total_eval)}
              </div>
            </div>

            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">🛒 보유자산 매입원가 (예수금 제외)</div>
              <div className="kpi-value" style={{ fontSize: '1.5rem' }}>
                {formatKRW(grand.total_buy)}
              </div>
            </div>

            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">📈 배당 포함 보유자산 손익 (수익률)</div>
              <div className="kpi-value" style={{ color: getProfitColor(grand.total_profit), fontSize: '1.5rem' }}>
                {(grand.total_profit || 0) > 0 ? '+' : ''}{formatKRW(grand.total_profit)}
                <span style={{ fontSize: '0.95rem', marginLeft: '6px', fontWeight: 600 }}>
                  ({formatPercent(grand.total_profit_pct)})
                </span>
              </div>
            </div>

            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">⚖️ 자산 배분 비중 현황</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '0.8rem', fontWeight: 700 }}>
                  {portfolios.map((p, idx) => (
                    <span key={p.id} style={{ color: portfolioColors[idx % portfolioColors.length] }}>
                      💼 {p.name} {p.weight_pct?.toFixed(1)}%
                    </span>
                  ))}
                  {includeCrypto && crypto && (
                    <span style={{ color: '#F59E0B' }}>
                      🪙 가상화폐 {crypto.weight_pct?.toFixed(1)}%
                    </span>
                  )}
                </div>
                <div style={{ height: '10px', background: 'rgba(255,255,255,0.08)', borderRadius: '5px', overflow: 'hidden', display: 'flex' }}>
                  {portfolios.map((p, idx) => (
                    <div
                      key={p.id}
                      style={{ width: `${p.weight_pct || 0}%`, background: portfolioColors[idx % portfolioColors.length] }}
                      title={`${p.name}: ${p.weight_pct?.toFixed(1)}%`}
                    />
                  ))}
                  {includeCrypto && crypto && (
                    <div
                      style={{ width: `${crypto.weight_pct || 0}%`, background: '#F59E0B' }}
                      title={`가상화폐: ${crypto.weight_pct?.toFixed(1)}%`}
                    />
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
