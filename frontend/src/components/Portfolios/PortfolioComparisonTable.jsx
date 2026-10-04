/** PortfolioComparisonTable: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { ArrowRight } from 'lucide-react';
import { formatKRW, formatPercent, getProfitColor } from '../../utils/formatters';

export default function PortfolioComparisonTable({
  portfolios,
  portfolioColors,
  onSelectPortfolio,
  includeCrypto,
  crypto,
  grand,
  isGrandProfit,
}) {
  return (
    <>
      {/* 3. Portfolios & Asset Class Overview Table */}
      <div className="section-card">
        <div className="section-title">
          <span>📊 포트폴리오 및 자산군별 비교 현황</span>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>포트폴리오 / 자산 구분</th>
                <th>운용 전략 (설명/메모)</th>
                <th>보유자산 매입원가(원)</th>
                <th>현재 평가금액(원)</th>
                <th>배당 포함 손익(원)</th>
                <th>수익률(%)</th>
                <th>보유 계좌/종목수</th>
                <th>전체 자산 비중(%)</th>
                <th>바로가기</th>
              </tr>
            </thead>
            <tbody>
              {portfolios.map((p, idx) => {
                return (
                  <tr key={p.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: portfolioColors[idx % portfolioColors.length] }} />
                        <strong style={{ fontSize: '0.96rem' }}>{p.name}</strong>
                        {p.is_default && (
                          <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>기본</span>
                        )}
                      </div>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      {p.description || '-'}
                    </td>
                    <td>{formatKRW(p.total_buy)}</td>
                    <td style={{ fontWeight: 700 }}>{formatKRW(p.total_eval)}</td>
                    <td style={{ color: getProfitColor(p.total_profit), fontWeight: 700 }}>
                      {(p.total_profit || 0) > 0 ? '+' : ''}{formatKRW(p.total_profit)}
                    </td>
                    <td style={{ color: getProfitColor(p.total_profit_pct), fontWeight: 700 }}>
                      {formatPercent(p.total_profit_pct)}
                    </td>
                    <td style={{ color: 'var(--text-secondary)' }}>
                      계좌 {p.account_count}개 / 종목 {p.asset_count}개
                    </td>
                    <td style={{ fontWeight: 700, color: portfolioColors[idx % portfolioColors.length] }}>
                      {p.weight_pct?.toFixed(2)}%
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectPortfolio(p.id)}
                        style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '4px 8px', fontSize: '0.78rem' }}
                      >
                        이동 <ArrowRight size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}

              {/* Crypto Row if included */}
              {includeCrypto && crypto && (
                <tr style={{ background: 'rgba(245, 158, 11, 0.04)' }}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#F59E0B' }} />
                      <strong style={{ fontSize: '0.96rem', color: '#F59E0B' }}>🪙 가상화폐 자산</strong>
                    </div>
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                    비트코인(BTC) 및 이더리움(ETH)
                  </td>
                  <td>{formatKRW(crypto.total_buy)}</td>
                  <td style={{ fontWeight: 700 }}>{formatKRW(crypto.total_eval)}</td>
                  <td style={{ color: getProfitColor(crypto.total_profit), fontWeight: 700 }}>
                    {(crypto.total_profit || 0) > 0 ? '+' : ''}{formatKRW(crypto.total_profit)}
                  </td>
                  <td style={{ color: getProfitColor(crypto.total_profit_pct), fontWeight: 700 }}>
                    {formatPercent(crypto.total_profit_pct)}
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>
                    코인 {crypto.assets?.length || 2}종
                  </td>
                  <td style={{ fontWeight: 700, color: '#F59E0B' }}>
                    {crypto.weight_pct?.toFixed(2)}%
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => onSelectPortfolio('crypto')}
                      style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '4px 8px', fontSize: '0.78rem' }}
                    >
                      이동 <ArrowRight size={12} />
                    </button>
                  </td>
                </tr>
              )}

              {/* Total Summary Row */}
              <tr className="total-row" style={{ fontSize: '1rem' }}>
                <td style={{ fontWeight: 800 }}>🌟 통합 전체 합계</td>
                <td>가문 전체 자산 종합</td>
                <td>{formatKRW(grand.total_buy)}</td>
                <td style={{ fontWeight: 800, color: 'var(--accent-primary)' }}>{formatKRW(grand.total_eval)}</td>
                <td style={{ color: isGrandProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {isGrandProfit ? '+' : ''}{formatKRW(grand.total_profit)}
                </td>
                <td style={{ color: isGrandProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {formatPercent(grand.total_profit_pct)}
                </td>
                <td>-</td>
                <td style={{ fontWeight: 800 }}>100.00%</td>
                <td>-</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
