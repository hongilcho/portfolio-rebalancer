/** InvestmentAssetsSection: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { formatKRW, formatUSD, formatQuantity, formatPercent, getProfitColor } from '../../utils/formatters';
import DriftBar from '../common/DriftBar';

export default function InvestmentAssetsSection({
  includeDeposits,
  currencyMode,
  displayStockAssets,
  investmentAssets,
  displayDualKpi,
  displayKpi,
  weightDriftAssets,
  drift_scale_max,
}) {
  return (
    <>
      {/* 3. Stock Assets Section */}
      <div className="section-card">
        <div className="section-title">
          <span>📈 투자 자산 현황 {includeDeposits ? '(주식/ETF/금/예금)' : '(주식/ETF/금 · 예금 제외)'}</span>

        </div>

        {/* 💻 DESKTOP TABLES (Screen > 768px) */}
        <div className="desktop-view">
          {/* Table 1: Basic Information */}
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
            [자산 기본 정보]
          </h4>
          <div className="table-container" style={{ marginBottom: '24px' }}>
            <table className="custom-table">
              <thead>
                <tr>
                  <th>종목명</th>
                  <th>보유 수량</th>
                  <th>수익률(%)</th>
                  <th>손익{currencyMode === 'USD' ? '' : '(원)'}</th>
                  <th>평가금액{currencyMode === 'USD' ? '' : '(원)'}</th>
                  <th>평단가{currencyMode === 'USD' ? '' : '(원)'}</th>
                  <th>현재가{currencyMode === 'USD' ? '' : '(원)'}</th>
                </tr>
              </thead>
              <tbody>
                {displayStockAssets?.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
                      현재 보유 중인 투자 자산이 없습니다. (보유 수량 0주 종목 제외)
                    </td>
                  </tr>
                ) : (
                  investmentAssets.map((item) => {
                  const isUs = item.market === 'US';
                  const isUsdMode = currencyMode === 'USD' && isUs;
                  const itemProfit = isUsdMode ? (item.profit_usd || 0) : (item.profit_krw || 0);
                  const itemReturn = isUsdMode ? (item.profit_pct_usd !== undefined ? item.profit_pct_usd : item.profit_pct) : item.profit_pct;

                  return (
                    <tr key={item.asset_id}>
                      <td style={{ fontWeight: 600 }}>
                        {item.name}
                        {isUs && (
                          <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                            US
                          </span>
                        )}
                        {(item.dividend_profit_krw > 0 || item.dividend_profit_usd > 0) && (
                          <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(16, 185, 129, 0.12)', color: 'var(--color-safe)', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
                            💰 배당반영
                          </span>
                        )}
                        {item.is_deposit && (
                          <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                            🏦 예금
                          </span>
                        )}
                        {item.is_deposit && item.account_no && (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                            계좌: {item.account_no}
                          </div>
                        )}
                      </td>
                      <td>{formatQuantity(item.quantity, item.unit)}</td>
                      <td style={{ color: getProfitColor(itemReturn), fontWeight: 700 }}>
                        <div>{formatPercent(itemReturn)}</div>
                        {(item.dividend_profit_krw > 0 || item.dividend_profit_usd > 0) && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                            시세 {formatPercent(isUsdMode ? item.eval_profit_pct_usd : item.eval_profit_pct)}
                          </div>
                        )}
                      </td>
                      <td style={{ color: getProfitColor(itemProfit), fontWeight: 700 }}>
                        <div>{isUsdMode ? formatUSD(item.profit_usd, true) : `${itemProfit > 0 ? '+' : ''}${formatKRW(item.profit_krw)}`}</div>
                        {(item.dividend_profit_krw > 0 || item.dividend_profit_usd > 0) ? (
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                            {isUsdMode
                              ? `시세 ${formatUSD(item.eval_profit_usd, true)} / 배당 +${formatUSD(item.dividend_profit_usd)}`
                              : `시세 ${formatKRW(item.eval_profit_krw, true)} / 배당 +${formatKRW(item.dividend_profit_krw)}`}
                          </div>
                        ) : (
                          isUs && (
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                              주가 {isUsdMode ? formatUSD(item.profit_usd, true) : formatKRW(item.pure_stock_profit_krw, true)} / 환차 {formatKRW(item.fx_profit_krw, true)}
                            </div>
                          )
                        )}
                      </td>
                      <td style={{ fontWeight: 600 }}>
                        {isUsdMode ? formatUSD(item.eval_amount_usd) : formatKRW(item.eval_amount)}
                      </td>
                      <td>
                        <div>{isUsdMode ? formatUSD(item.avg_price_usd) : formatKRW(item.avg_price)}</div>
                        {item.cumulative_dividend > 0 && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--color-safe, #10b981)', whiteSpace: 'nowrap' }}>
                            누적배당: +{isUsdMode || isUs ? formatUSD(item.cumulative_dividend) : formatKRW(item.cumulative_dividend)}/주
                          </div>
                        )}
                        {isUs && item.buy_fx_rate > 0 && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                            {isUsdMode ? `매입환율: ${formatKRW(item.buy_fx_rate)}` : `$${item.avg_price_usd} (@ ${formatKRW(item.buy_fx_rate)})`}
                          </div>
                        )}
                      </td>
                      <td>
                        {isUsdMode ? formatUSD(item.current_price_usd) : formatKRW(item.current_price)}
                      </td>
                    </tr>
                  );
                }))}
                {/* Total Row */}
                {displayStockAssets?.length > 0 && (
                  <tr className="total-row">
                    <td>{includeDeposits ? '총합계' : '총합계 (예금 제외)'}</td>
                    <td>-</td>
                    <td style={{ fontWeight: 700 }}>
                      {currencyMode === 'USD' ? (
                        <span>
                          <span style={{ color: getProfitColor(displayDualKpi.usd.total_return) }}>
                            🇺🇸 {formatPercent(displayDualKpi.usd.total_return)}
                          </span>
                          <span style={{ margin: '0 6px', color: 'var(--text-muted)' }}>|</span>
                          <span style={{ color: getProfitColor(displayDualKpi.krw.total_return) }}>
                            🇰🇷 {formatPercent(displayDualKpi.krw.total_return)}
                          </span>
                        </span>
                      ) : (
                        <span style={{ color: getProfitColor(displayKpi?.total_stock_return) }}>
                          {formatPercent(displayKpi?.total_stock_return)}
                        </span>
                      )}
                    </td>
                    <td style={{ fontWeight: 700 }}>
                      {currencyMode === 'USD' ? (
                        <span>
                          <span style={{ color: getProfitColor(displayDualKpi.usd.total_profit) }}>
                            🇺🇸 {formatUSD(displayDualKpi.usd.total_profit, true)}
                          </span>
                          <span style={{ margin: '0 6px', color: 'var(--text-muted)' }}>|</span>
                          <span style={{ color: getProfitColor(displayDualKpi.krw.total_profit) }}>
                            🇰🇷 {formatKRW(displayDualKpi.krw.total_profit, true)}
                          </span>
                        </span>
                      ) : (
                        <span style={{ color: getProfitColor(displayKpi?.total_stock_profit) }}>
                          {(displayKpi?.total_stock_profit || 0) > 0 ? '+' : ''}{formatKRW(displayKpi?.total_stock_profit)}
                        </span>
                      )}
                    </td>
                    <td style={{ fontWeight: 700 }}>
                      {currencyMode === 'USD' ? (
                        <span>
                          🇺🇸 {formatUSD(displayDualKpi.usd.total_eval)}
                          <span style={{ margin: '0 4px', color: 'var(--text-muted)' }}>|</span>
                          🇰🇷 {formatKRW(displayDualKpi.krw.total_eval)}
                        </span>
                      ) : (
                        formatKRW(displayKpi?.total_stock_eval)
                      )}
                    </td>
                    <td>-</td>
                    <td>-</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Table 2: Weights & Bidirectional Drift Chart */}
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
            [비중 및 괴리율]
          </h4>
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>종목명</th>
                  <th style={{ textAlign: 'center' }}>현 비중(%)</th>
                  <th style={{ textAlign: 'center' }}>목표비중(%)</th>
                  <th style={{ textAlign: 'center', width: '220px' }}>괴리율(%)</th>
                </tr>
              </thead>
              <tbody>
                {weightDriftAssets?.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                      현재 보유 중인 자산이 없습니다. (보유 수량 0주 종목 제외)
                    </td>
                  </tr>
                ) : (
                  weightDriftAssets.map((item) => (
                    <tr key={item.asset_id}>
                      <td style={{ fontWeight: 600 }}>{item.name}</td>
                      <td style={{ textAlign: 'center', fontWeight: 600 }}>
                        {item.weight_pct.toFixed(1)}%
                      </td>
                      <td style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
                        {item.target_weight_pct.toFixed(1)}%
                      </td>
                      <td>
                        <DriftBar drift={item.drift_pct} scaleMax={drift_scale_max} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* 📱 MOBILE RESPONSIVE CARDS (Screen <= 768px) */}
        <div className="mobile-view">
          {displayStockAssets?.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '28px 16px', color: 'var(--text-muted)', background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', margin: '10px 0' }}>
              현재 보유 중인 투자 자산이 없습니다. (보유 수량 0주 종목 제외)
            </div>
          ) : (
            investmentAssets.map((item) => {
            const isUs = item.market === 'US';
            const isUsdMode = currencyMode === 'USD' && isUs;
            const itemProfit = isUsdMode ? (item.profit_usd || 0) : (item.profit_krw || 0);
            const incRebal = item.include_in_rebalance !== false;

            return (
              <div key={item.asset_id} className="mobile-card-item">
                {/* Row 1: Name + Eval Amount */}
                <div className="mobile-card-row">
                  <div className="mobile-card-title">
                    <span>{item.name}</span>
                    {isUs && (
                      <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                        US
                      </span>
                    )}
                    {(item.dividend_profit_krw > 0 || item.dividend_profit_usd > 0) && (
                      <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(16, 185, 129, 0.12)', color: 'var(--color-safe)', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
                        💰 배당반영
                      </span>
                    )}
                    {item.is_deposit ? (
                      <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                        🏦 예금 {item.account_no ? `(${item.account_no})` : ''}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '6px', whiteSpace: 'nowrap' }}>({item.ticker})</span>
                    )}
                    {!incRebal && (
                      <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(156, 163, 175, 0.2)', color: 'var(--text-muted)' }}>
                        비중 제외
                      </span>
                    )}
                  </div>
                  <span className="mobile-card-value">
                    {isUsdMode ? formatUSD(item.eval_amount_usd) : formatKRW(item.eval_amount)}
                  </span>
                </div>

                {/* Row 2: Quantity & Prices + Profit/Loss */}
                <div className="mobile-card-row">
                  <span className="mobile-card-subtext">
                    <span>{formatQuantity(item.quantity, item.unit)}</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span>평단 {isUsdMode ? formatUSD(item.avg_price_usd) : formatKRW(item.avg_price)}</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span>현재 {isUsdMode ? formatUSD(item.current_price_usd) : formatKRW(item.current_price)}</span>
                  </span>
                  <span className="mobile-card-stat" style={{ color: getProfitColor(itemProfit) }}>
                    {isUsdMode ? (
                      `${formatUSD(item.profit_usd, true)} (${formatPercent(item.profit_pct_usd !== undefined ? item.profit_pct_usd : item.profit_pct)})`
                    ) : (
                      `${itemProfit > 0 ? '+' : ''}${formatKRW(item.profit_krw)} (${formatPercent(item.profit_pct)})`
                    )}
                  </span>
                </div>

                {/* Dividend Details Info */}
                {(item.dividend_profit_krw > 0 || item.dividend_profit_usd > 0) && (
                  <div style={{ fontSize: '0.74rem', color: 'var(--color-safe, #10b981)', marginTop: '2px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px' }}>
                    <span>
                      배당수익: +{isUsdMode || isUs ? formatUSD(item.dividend_profit_usd) : formatKRW(item.dividend_profit_krw)}
                      {item.cumulative_dividend > 0 && ` (주당 +${isUsdMode || isUs ? formatUSD(item.cumulative_dividend) : formatKRW(item.cumulative_dividend)})`}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      시세손익: {isUsdMode ? formatUSD(item.eval_profit_usd, true) : formatKRW(item.eval_profit_krw, true)}
                    </span>
                  </div>
                )}

                {/* US Asset FX Rate & Profit Decomposition */}
                {isUs && (
                  <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: '4px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px' }}>
                    <span>매입환율: {formatKRW(item.buy_fx_rate || 0)}</span>
                    <span>
                      주가 {isUsdMode ? formatUSD(item.profit_usd, true) : formatKRW(item.pure_stock_profit_krw, true)}
                      {' · '}
                      환차 {formatKRW(item.fx_profit_krw, true)}
                    </span>
                  </div>
                )}

                {/* Row 3: Weight info & Drift (투자 자산만 표시, 예금형 자산은 완전 제외) */}
                {!item.is_deposit && incRebal && (
                  <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-color)' }}>
                    <div className="mobile-card-row" style={{ fontSize: '0.82rem', marginBottom: '6px' }}>
                      <span style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        현재 <strong>{item.weight_pct.toFixed(1)}%</strong> / 목표 <strong>{item.target_weight_pct.toFixed(1)}%</strong>
                      </span>
                      <span style={{ fontWeight: 700, whiteSpace: 'nowrap', color: item.drift_pct > 0 ? 'var(--color-profit)' : item.drift_pct < 0 ? 'var(--color-loss)' : 'var(--text-muted)' }}>
                        괴리율: {item.drift_pct > 0 ? '+' : ''}{item.drift_pct.toFixed(1)}%
                      </span>
                    </div>
                    <DriftBar drift={item.drift_pct} scaleMax={drift_scale_max} />
                  </div>
                )}
              </div>
            );
          }))}
        </div>
      </div>
    </>
  );
}
