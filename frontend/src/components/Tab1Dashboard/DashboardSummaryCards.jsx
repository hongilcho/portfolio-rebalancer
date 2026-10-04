/** DashboardSummaryCards: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { formatKRW, formatUSD, formatPercent, getProfitColor } from '../../utils/formatters';

export default function DashboardSummaryCards({
  currencyMode,
  displayDualKpi,
  includeDeposits,
  displayKpi,
}) {
  return (
    <>
      {/* 1. Top KPI Summary Cards (USD 모드: 방안 1 2단 압축 카드 / KRW 모드: 기본 4개 카드) */}
      {currencyMode === 'USD' ? (
        <div className="dual-currency-kpi-grid">
          {/* 1) 🇺🇸 외화 자산 종합 (USD) */}
          <div className="dual-kpi-card usd-card">
            <div className="dual-kpi-header">
              <div className="dual-kpi-title">
                <span className="badge badge-accent">🇺🇸 외화 자산 종합 (USD)</span>
                <span className="dual-kpi-subtitle">미국 상장 자산 & 외화 예수금</span>
              </div>
              <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: 'var(--accent-primary)', fontSize: '0.74rem' }}>
                외화 순자산 {formatUSD(displayDualKpi.usd.total_eval + displayDualKpi.usd.cash)}
              </span>
            </div>
            <div className="dual-kpi-main">
              <div className="dual-kpi-main-label">외화 총 평가금액</div>
              <div className="dual-kpi-main-value" style={{ color: 'var(--accent-primary)' }}>
                {formatUSD(displayDualKpi.usd.total_eval)}
              </div>
              <div className="dual-kpi-sub-row">
                <span className="dual-kpi-sub-label">외화 배당 포함 손익:</span>
                <span className="dual-kpi-sub-value" style={{ color: getProfitColor(displayDualKpi.usd.total_profit) }}>
                  {formatUSD(displayDualKpi.usd.total_profit, true)} ({formatPercent(displayDualKpi.usd.total_return)})
                </span>
              </div>
              {displayDualKpi.usd.dividend_profit > 0 && (
                <div className="dual-kpi-sub-row" style={{ marginTop: '2px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                  <span className="dual-kpi-sub-label">↳ 시세 / 배당:</span>
                  <span className="dual-kpi-sub-value">
                    {formatUSD(displayDualKpi.usd.eval_profit, true)} / +{formatUSD(displayDualKpi.usd.dividend_profit)}
                  </span>
                </div>
              )}
              {displayDualKpi.usd.total_buy > 0 && (
                <div className="dual-kpi-sub-row" style={{ marginTop: '4px', fontSize: '0.78rem' }}>
                  <span className="dual-kpi-sub-label">💱 환차익(원화):</span>
                  <span className="dual-kpi-sub-value" style={{ color: getProfitColor(displayDualKpi.usd.total_fx_profit_krw) }}>
                    {formatKRW(displayDualKpi.usd.total_fx_profit_krw, true)} ({formatPercent(displayDualKpi.usd.total_fx_profit_pct)})
                  </span>
                </div>
              )}
            </div>
            <div className="dual-kpi-footer">
              <div className="dual-kpi-footer-item">
                <span>외화 투자원금</span>
                <strong>{formatUSD(displayDualKpi.usd.total_buy)}</strong>
                {displayDualKpi.usd.weighted_buy_fx_rate > 0 && (
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                    @ {formatKRW(displayDualKpi.usd.weighted_buy_fx_rate)}/$
                  </span>
                )}
              </div>
              <div className="dual-kpi-footer-divider" />
              <div className="dual-kpi-footer-item">
                <span>외화 예수금</span>
                <strong style={{ color: 'var(--accent-primary)' }}>{formatUSD(displayDualKpi.usd.cash)}</strong>
              </div>
            </div>
          </div>

          {/* 2) 🇰🇷 원화 자산 종합 (KRW) */}
          <div className="dual-kpi-card krw-card">
            <div className="dual-kpi-header">
              <div className="dual-kpi-title">
                <span className="badge badge-safe">🇰🇷 원화 자산 종합 (KRW)</span>
                <span className="dual-kpi-subtitle">국내 주식·채권·금현물·예금 & 원화 예수금</span>
              </div>
              <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-safe)', fontSize: '0.74rem' }}>
                원화 순자산 {formatKRW(displayDualKpi.krw.total_eval + displayDualKpi.krw.cash)}
              </span>
            </div>
            <div className="dual-kpi-main">
              <div className="dual-kpi-main-label">원화 총 평가금액 {includeDeposits ? '' : '(예금 제외)'}</div>
              <div className="dual-kpi-main-value" style={{ color: 'var(--color-safe)' }}>
                {formatKRW(displayDualKpi.krw.total_eval)}
              </div>
              <div className="dual-kpi-sub-row">
                <span className="dual-kpi-sub-label">원화 배당 포함 손익:</span>
                <span className="dual-kpi-sub-value" style={{ color: getProfitColor(displayDualKpi.krw.total_profit) }}>
                  {formatKRW(displayDualKpi.krw.total_profit, true)} ({formatPercent(displayDualKpi.krw.total_return)})
                </span>
              </div>
              {displayDualKpi.krw.dividend_profit > 0 && (
                <div className="dual-kpi-sub-row" style={{ marginTop: '2px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                  <span className="dual-kpi-sub-label">↳ 시세 / 배당:</span>
                  <span className="dual-kpi-sub-value">
                    {formatKRW(displayDualKpi.krw.eval_profit, true)} / +{formatKRW(displayDualKpi.krw.dividend_profit)}
                  </span>
                </div>
              )}
            </div>
            <div className="dual-kpi-footer">
              <div className="dual-kpi-footer-item">
                <span>원화 투자원금</span>
                <strong>{formatKRW(displayDualKpi.krw.total_buy)}</strong>
              </div>
              <div className="dual-kpi-footer-divider" />
              <div className="dual-kpi-footer-item">
                <span>원화 예수금</span>
                <strong style={{ color: 'var(--color-safe)' }}>{formatKRW(displayDualKpi.krw.cash)}</strong>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-title">🛒 총 투자 매입금액 {includeDeposits ? '(원금)' : '(예금 제외)'}</div>
            <div className="kpi-value">{formatKRW(displayKpi?.total_stock_buy)}</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-title">📈 총 투자 평가금액 {includeDeposits ? '' : '(예금 제외)'}</div>
            <div className="kpi-value">{formatKRW(displayKpi?.total_stock_eval)}</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-title">총 손익 (Total Return) {includeDeposits ? '' : '(예금 제외)'}</div>
            <div className="kpi-value" style={{ color: getProfitColor(displayKpi?.total_stock_profit) }}>
              {(displayKpi?.total_stock_profit || 0) > 0 ? '+' : ''}{formatKRW(displayKpi?.total_stock_profit)}
            </div>
            {displayKpi?.total_dividend_profit > 0 && (
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                시세 {formatKRW(displayKpi?.total_eval_profit, true)} | 배당 +{formatKRW(displayKpi?.total_dividend_profit)}
              </div>
            )}
          </div>

          <div className="kpi-card">
            <div className="kpi-title">총 수익률 (Total Return) {includeDeposits ? '' : '(예금 제외)'}</div>
            <div className="kpi-value" style={{ color: getProfitColor(displayKpi?.total_stock_return) }}>
              {formatPercent(displayKpi?.total_stock_return)}
            </div>
            {displayKpi?.total_dividend_profit > 0 && (
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                시세수익률 {formatPercent(displayKpi?.total_eval_return)}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
