/** AggregatedAssetsTable: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { TrendingUp } from 'lucide-react';
import { formatKRW, formatUSD, formatPercent, getProfitColor } from '../../utils/formatters';

export default function AggregatedAssetsTable({ currencyMode, aggregatedAssets }) {
  return (
    <>
      {/* 3. [USER REQUIREMENT] Aggregated Asset Breakdown Table */}
      <div className="section-card">
        <div className="section-title">
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TrendingUp size={18} color="var(--accent-primary)" />
            📈 종목별 통합 합산 현황 (여러 포트폴리오에 분산된 동일 종목 통합 집계)
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            여러 포트폴리오에 나누어 보유 중인 동일 종목을 가중평균 평단가와 통합 수량으로 합산한 지표입니다.
          </span>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>종목명 (티커)</th>
                <th>시장</th>
                <th>통합 보유수량</th>
                <th>통합 평단가 (가중평균)</th>
                <th>실시간 현재가</th>
                <th>총 평가금액{currencyMode === 'USD' ? '' : '(원)'}</th>
                <th>배당 포함 손익{currencyMode === 'USD' ? '' : '(원)'}</th>
                <th>수익률(%)</th>
                <th>전체 자산 비중(%)</th>
                <th>포트폴리오별 보유 분산</th>
              </tr>
            </thead>
            <tbody>
              {aggregatedAssets.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '30px', color: 'var(--text-secondary)' }}>
                    보유 중인 종목이 없습니다.
                  </td>
                </tr>
              ) : (
                aggregatedAssets.map((item) => {
                  const isUs = item.market === 'US';
                  const isUsdMode = currencyMode === 'USD' && isUs;
                  const isCryptoItem = item.asset_type === 'CRYPTO';
                  const rowProfit = isUsdMode ? (item.total_profit_usd || 0) : (item.total_profit || 0);
                  const rowReturn = isUsdMode ? (item.total_profit_pct_usd || 0) : (item.total_profit_pct || 0);

                  return (
                    <tr key={item.key}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '1.1rem' }}>
                            {isCryptoItem ? (item.ticker === 'BTC' ? '🪙' : '💎') : '📈'}
                          </span>
                          <div>
                            <strong style={{ fontSize: '0.94rem', color: isCryptoItem ? '#F59E0B' : 'inherit' }}>
                              {item.name}
                            </strong>
                            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                              {item.ticker}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${item.market === 'US' ? 'badge-primary' : (isCryptoItem ? 'badge-warning' : 'badge-secondary')}`}>
                          {item.market}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600 }}>
                        {isCryptoItem
                          ? `${Number(item.total_quantity).toFixed(8).replace(/\.?0+$/, '')} ${item.ticker}`
                          : `${Number(item.total_quantity).toLocaleString()}주`}
                      </td>
                      <td>
                        <div>{isUsdMode ? formatUSD(item.weighted_avg_price_usd) : formatKRW(item.weighted_avg_price)}</div>
                        {isUs && item.buy_fx_rate > 0 && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                            {isUsdMode ? `매입환율: ${formatKRW(item.buy_fx_rate)}` : `$${item.weighted_avg_price_usd} (@ ${formatKRW(item.buy_fx_rate)})`}
                          </div>
                        )}
                      </td>
                      <td>{isUsdMode ? formatUSD(item.current_price_usd) : formatKRW(item.current_price)}</td>
                      <td style={{ fontWeight: 700, color: 'var(--accent-primary)' }}>
                        {isUsdMode ? formatUSD(item.total_eval_amount_usd) : formatKRW(item.total_eval_amount)}
                      </td>
                      <td style={{ color: getProfitColor(rowProfit), fontWeight: 700 }}>
                        <div>{isUsdMode ? formatUSD(item.total_profit_usd, true) : `${rowProfit > 0 ? '+' : ''}${formatKRW(item.total_profit)}`}</div>
                        {isUs && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                            주가 {isUsdMode ? formatUSD(item.eval_profit_usd, true) : formatKRW(item.pure_stock_profit_krw, true)} / 환차 {formatKRW(item.fx_profit_krw, true)} / 배당 {isUsdMode ? formatUSD(item.total_dividend_profit_usd) : formatKRW(item.total_dividend_profit)}
                          </div>
                        )}
                      </td>
                      <td style={{ color: getProfitColor(rowReturn), fontWeight: 700 }}>
                        {formatPercent(rowReturn)}
                      </td>
                      <td style={{ fontWeight: 700 }}>
                        {item.weight_in_grand_total_pct?.toFixed(2)}%
                      </td>
                      <td>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                          {item.distribution?.map((d, dIdx) => (
                            <span
                              key={dIdx}
                              className="badge"
                              style={{
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border-color)',
                                fontSize: '0.74rem',
                                color: 'var(--text-secondary)'
                              }}
                              title={isUsdMode ? `평단가: ${formatUSD(d.avg_price_usd)}, 평가액: ${formatUSD(d.eval_amount_usd)}` : `평단가: ${formatKRW(d.avg_price)}, 평가액: ${formatKRW(d.eval_amount)}`}
                            >
                              <strong>{d.portfolio_name}</strong>: {isCryptoItem ? `${d.quantity} ${item.ticker}` : `${d.quantity}주`}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
