/** AccountBreakdown: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { ShieldAlert, ChevronDown, ChevronUp } from 'lucide-react';
import { formatKRW, formatUSD, formatQuantity, formatPercent, getProfitColor } from '../../utils/formatters';

export default function AccountBreakdown({
  includeDeposits,
  displayAccSummaries,
  expandedAccs,
  usd_krw,
  toggleAccordion,
  currencyMode,
}) {
  return (
    <>
      {/* 4. Accounts Breakdown Section */}
      <div className="section-card">
        <div className="section-title">
          <span>💳 계좌별 자산 현황 & 한도 모니터링</span>

        </div>

        {!includeDeposits && (
          <div style={{
            marginBottom: '14px',
            padding: '8px 12px',
            background: 'rgba(99, 102, 241, 0.08)',
            border: '1px solid rgba(99, 102, 241, 0.2)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.82rem',
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <span>💡 <strong>예금 제외 모드:</strong> 정기예금 전용 계좌 및 각 계좌 내 예금 보유분이 제외된 순수 투자자산 기준입니다.</span>
          </div>
        )}

        {displayAccSummaries.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', padding: '12px 0' }}>
            {includeDeposits ? '등록된 계좌가 없습니다.' : '등록된 투자 계좌가 없습니다. (예금 제외 모드)'}
          </p>
        ) : (
          displayAccSummaries.map((acc) => {
            const isExpanded = expandedAccs[acc.id] !== false; // default true
            const isIrp = acc.account_type === 'IRP';
            const isIrpOverRisk = isIrp && acc.risk_pct > 70.0;
            const accStockProfit = acc.profit_krw || ((acc.stock_eval || 0) - (acc.stock_buy_total || 0));
            const accStockReturn = acc.profit_pct || (acc.stock_buy_total > 0 ? (accStockProfit / acc.stock_buy_total * 100) : 0);
            const totalVal = acc.total_val || (acc.stock_eval + acc.deposit_krw + (acc.deposit_usd * (usd_krw || 1380)));

            const annualPct = (acc.annual_limit_pct || 0) * 100;
            const taxPct = (acc.tax_limit_pct || 0) * 100;

            return (
              <div key={acc.id} className="account-accordion">
                {/* Accordion Header */}
                <div className="accordion-header" onClick={() => toggleAccordion(acc.id)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: '1.05rem' }}>
                      📌 [{acc.account_type === '정기예금' ? '🏦 정기예금' : acc.account_type}] {acc.account_alias}
                    </span>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      ({acc.account_no})
                    </span>
                    {acc.account_type !== '정기예금' && (
                      <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.15)', color: 'var(--accent-primary)' }}>
                        우선순위: {acc.priority || 99}
                      </span>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block' }}>계좌 총 자산</span>
                      <span style={{ fontWeight: 800, fontSize: '1.05rem', color: 'var(--text-primary)' }}>{formatKRW(totalVal)}</span>
                    </div>
                    {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                  </div>
                </div>

                {/* Accordion Body */}
                {isExpanded && (
                  <div className="accordion-body">
                    {/* Account Stat Highlight Row */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', background: 'var(--bg-surface)', padding: '14px 16px', borderRadius: 'var(--radius-md)', marginBottom: '16px', border: '1px solid var(--border-color)' }}>
                      <div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          {acc.account_type === '정기예금' ? '🏦 예금 평가금액' : '📈 주식 평가금액'}
                        </div>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700 }}>{formatKRW(acc.stock_eval)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>총손익 (수익률)</div>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700, color: getProfitColor(accStockProfit) }}>
                          {(accStockProfit || 0) > 0 ? '+' : ''}{formatKRW(accStockProfit)} ({formatPercent(accStockReturn)})
                        </div>
                        {acc.dividend_profit_krw > 0 && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                            시세 {formatKRW(acc.eval_profit_krw, true)} | 배당 +{formatKRW(acc.dividend_profit_krw)}
                          </div>
                        )}
                      </div>
                      <div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>💵 보유 예수금</div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>
                          원화 {formatKRW(acc.deposit_krw)} {acc.deposit_usd > 0 && `| 달러 ${formatUSD(acc.deposit_usd)}`}
                        </div>
                      </div>
                    </div>

                    {/* IRP Risk Banner */}
                    {isIrp && (
                      <div className={`alert-banner ${isIrpOverRisk ? 'alert-danger' : 'alert-success'}`} style={{ marginBottom: '16px' }}>
                        <ShieldAlert size={18} />
                        <span>
                          <strong>IRP 위험자산 비중: {acc.risk_pct?.toFixed(1) || 0}%</strong> / 70.0% 제한 —{' '}
                          {isIrpOverRisk ? '⚠️ 70% 초과! 안전자산 비중을 늘려주세요.' : '✅ 규정 준수 중'}
                        </span>
                      </div>
                    )}

                    {/* Limits Progress Bars */}
                    {acc.annual_limit > 0 && (
                      <div className="progress-bar-container">
                        <div className="progress-bar-label">
                          <span>연간 납입한도 ({formatKRW(acc.annual_limit)} 중 약 {annualPct.toFixed(1)}% 소진)</span>
                          <strong>{annualPct.toFixed(1)}%</strong>
                        </div>
                        <div className="progress-track">
                          <div
                            className="progress-fill"
                            style={{
                            width: `${Math.min(100, annualPct)}%`,
                            background: annualPct > 100 ? 'var(--color-risk)' : 'var(--accent-primary)'
                          }}
                        />
                      </div>
                    </div>
                  )}

                  {acc.tax_limit > 0 && (
                    <div className="progress-bar-container">
                      <div className="progress-bar-label">
                        <span>세액공제 한도 ({formatKRW(acc.tax_limit)} 중 약 {taxPct.toFixed(1)}% 소진)</span>
                        <strong>{taxPct.toFixed(1)}%</strong>
                      </div>
                      <div className="progress-track">
                        <div
                          className="progress-fill"
                          style={{
                            width: `${Math.min(100, taxPct)}%`,
                            background: taxPct > 100 ? 'var(--color-risk)' : '#10B981'
                          }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Limit Exhaustion Toggle (96% 이상 또는 소진 완료 시) */}
                  {acc.can_exhaust_limit && (
                    <div style={{
                      marginTop: '12px',
                      marginBottom: '4px',
                      padding: '10px 14px',
                      background: acc.is_limit_exhausted ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                      border: `1px solid ${acc.is_limit_exhausted ? 'rgba(16, 185, 129, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
                      borderRadius: 'var(--radius-md)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '8px'
                    }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.86rem', fontWeight: 600, color: acc.is_limit_exhausted ? '#10B981' : 'var(--text-primary)' }}>
                        <input
                          type="checkbox"
                          checked={!!acc.is_limit_exhausted}
                          disabled aria-label="한도 소진 상태 · 5번 탭에서 변경"
                          style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                        />
                        <span>
                          {acc.is_limit_exhausted
                            ? '🔒 연간 납입한도 소진 완료 (리밸런싱 추가 입금 차단 중)'
                            : '💡 한도 96% 이상 도달 · 상태 변경은 5번 탭에서 처리'}
                        </span>
                      </label>
                      {acc.is_limit_exhausted && (
                        <span className="badge" style={{ background: '#10B981', color: '#fff', fontSize: '0.75rem', padding: '2px 8px' }}>
                          100% 소진 완료
                        </span>
                      )}
                    </div>
                  )}

                  {/* Account Holdings List */}
                  <div style={{ marginTop: '16px' }}>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '10px' }}>
                      📦 계좌별 보유 종목 ({acc.holdings?.length || 0}개)
                    </div>

                    {/* Desktop Holdings Table */}
                    <div className="desktop-view">
                      <div className="table-container">
                        <table className="custom-table" style={{ fontSize: '0.86rem' }}>
                          <thead>
                            <tr>
                              <th>종목명</th>
                              <th>티커</th>
                              <th>보유수량</th>
                              <th>평단가</th>
                              <th>현재가</th>
                              <th>평가금액</th>
                              <th>손익(수익률)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {acc.holdings?.map((h) => {
                              const isHUs = h.market === 'US';
                              const isHUsdMode = currencyMode === 'USD' && isHUs;

                              return (
                                <tr key={h.asset_id}>
                                  <td style={{ fontWeight: 700 }}>
                                    {h.asset_name}
                                    {isHUs && (
                                      <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                        US
                                      </span>
                                    )}
                                    {(h.dividend_profit_krw > 0 || h.dividend_profit_usd > 0) && (
                                      <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(16, 185, 129, 0.12)', color: 'var(--color-safe)', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
                                        💰 배당반영
                                      </span>
                                    )}
                                    {h.is_deposit && (
                                      <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                        🏦 예금
                                      </span>
                                    )}
                                  </td>
                                  <td>{h.ticker}</td>
                                  <td>{formatQuantity(h.quantity, h.unit)}</td>
                                  <td>
                                    <div>{isHUsdMode ? formatUSD(h.avg_price_usd) : formatKRW(h.avg_price)}</div>
                                    {h.cumulative_dividend > 0 && (
                                      <div style={{ fontSize: '0.72rem', color: 'var(--color-safe, #10b981)', whiteSpace: 'nowrap' }}>
                                        누적배당: +{isHUsdMode || isHUs ? formatUSD(h.cumulative_dividend) : formatKRW(h.cumulative_dividend)}/주
                                      </div>
                                    )}
                                    {isHUs && h.buy_fx_rate > 0 && (
                                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                                        {isHUsdMode ? `매입환율: ${formatKRW(h.buy_fx_rate)}` : `$${h.avg_price_usd} (@ ${formatKRW(h.buy_fx_rate)})`}
                                      </div>
                                    )}
                                  </td>
                                  <td>{isHUsdMode ? formatUSD(h.current_price_usd) : formatKRW(h.current_price)}</td>
                                  <td style={{ fontWeight: 700 }}>{isHUsdMode ? formatUSD(h.eval_amount_usd) : formatKRW(h.eval_amount)}</td>
                                  <td style={{ color: getProfitColor(isHUsdMode ? h.profit_usd : h.profit_krw), fontWeight: 700 }}>
                                    <div>{isHUsdMode ? formatUSD(h.profit_usd, true) : `${(h.profit_krw || 0) > 0 ? '+' : ''}${formatKRW(h.profit_krw)}`} ({formatPercent(isHUsdMode ? h.profit_pct_usd : h.profit_pct)})</div>
                                    {(h.dividend_profit_krw > 0 || h.dividend_profit_usd > 0) ? (
                                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                                        {isHUsdMode
                                          ? `시세 ${formatUSD(h.eval_profit_usd, true)} / 배당 +${formatUSD(h.dividend_profit_usd)}`
                                          : `시세 ${formatKRW(h.eval_profit_krw, true)} / 배당 +${formatKRW(h.dividend_profit_krw)}`}
                                      </div>
                                    ) : (
                                      isHUs && (
                                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                                          주가 {isHUsdMode ? formatUSD(h.profit_usd, true) : formatKRW(h.pure_stock_profit_krw, true)} / 환차 {formatKRW(h.fx_profit_krw, true)}
                                        </div>
                                      )
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                            <tr>
                              <td style={{ fontWeight: 700 }} colSpan={5}>💵 원화 예수금</td>
                              <td style={{ fontWeight: 800 }}>{formatKRW(acc.deposit_krw)}</td>
                              <td>-</td>
                            </tr>
                            {(Number(acc.deposit_usd) > 0 || currencyMode === 'USD') && (
                              <tr>
                                <td style={{ fontWeight: 700 }} colSpan={5}>💵 외화 예수금 (USD)</td>
                                <td style={{ fontWeight: 800, color: 'var(--accent-primary)' }}>{formatUSD(acc.deposit_usd)}</td>
                                <td>-</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Mobile Holdings Cards */}
                    <div className="mobile-view">
                      {acc.holdings?.map((h) => {
                        const isHUs = h.market === 'US';
                        const isHUsdMode = currencyMode === 'USD' && isHUs;

                        return (
                          <div key={h.asset_id} className="mobile-card-item" style={{ background: 'var(--bg-surface)' }}>
                            <div className="mobile-card-row">
                              <div className="mobile-card-title">
                                <span>{h.asset_name}</span>
                                {isHUs && (
                                  <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                    US
                                  </span>
                                )}
                                {(h.dividend_profit_krw > 0 || h.dividend_profit_usd > 0) && (
                                  <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(16, 185, 129, 0.12)', color: 'var(--color-safe)', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
                                    💰 배당반영
                                  </span>
                                )}
                                {h.is_deposit ? (
                                  <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                    🏦 예금
                                  </span>
                                ) : (
                                  <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginLeft: '6px', whiteSpace: 'nowrap' }}>({h.ticker})</span>
                                )}
                              </div>
                              <span className="mobile-card-value">
                                {isHUsdMode ? formatUSD(h.eval_amount_usd) : formatKRW(h.eval_amount)}
                              </span>
                            </div>
                            <div className="mobile-card-row">
                              <span className="mobile-card-subtext">
                                <span>{formatQuantity(h.quantity, h.unit)}</span>
                                <span style={{ color: 'var(--text-muted)' }}>·</span>
                                <span>평단 {isHUsdMode ? formatUSD(h.avg_price_usd) : formatKRW(h.avg_price)}</span>
                                <span style={{ color: 'var(--text-muted)' }}>·</span>
                                <span>현재 {isHUsdMode ? formatUSD(h.current_price_usd) : formatKRW(h.current_price)}</span>
                              </span>
                              <span className="mobile-card-stat" style={{ color: getProfitColor(isHUsdMode ? h.profit_usd : h.profit_krw) }}>
                                {isHUsdMode ? (
                                  `${formatUSD(h.profit_usd, true)} (${formatPercent(h.profit_pct_usd !== undefined ? h.profit_pct_usd : h.profit_pct)})`
                                ) : (
                                  `${(h.profit_krw || 0) > 0 ? '+' : ''}${formatKRW(h.profit_krw)} (${formatPercent(h.profit_pct)})`
                                )}
                              </span>
                            </div>

                            {/* Dividend Details Info */}
                            {(h.dividend_profit_krw > 0 || h.dividend_profit_usd > 0) && (
                              <div style={{ fontSize: '0.74rem', color: 'var(--color-safe, #10b981)', marginTop: '2px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px' }}>
                                <span>
                                  배당수익: +{isHUsdMode || isHUs ? formatUSD(h.dividend_profit_usd) : formatKRW(h.dividend_profit_krw)}
                                  {h.cumulative_dividend > 0 && ` (주당 +${isHUsdMode || isHUs ? formatUSD(h.cumulative_dividend) : formatKRW(h.cumulative_dividend)})`}
                                </span>
                                <span style={{ color: 'var(--text-secondary)' }}>
                                  시세손익: {isHUsdMode ? formatUSD(h.eval_profit_usd, true) : formatKRW(h.eval_profit_krw, true)}
                                </span>
                              </div>
                            )}
                            {isHUs && (
                              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: '4px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px' }}>
                                <span>매입환율: {formatKRW(h.buy_fx_rate || 0)}</span>
                                <span>
                                  주가 {isHUsdMode ? formatUSD(h.profit_usd, true) : formatKRW(h.pure_stock_profit_krw, true)}
                                  {' · '}
                                  환차 {formatKRW(h.fx_profit_krw, true)}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                      <div className="mobile-card-item" style={{ background: 'var(--bg-surface)' }}>
                        <div className="mobile-card-row">
                          <span style={{ fontWeight: 700 }}>💵 원화 예수금</span>
                          <span className="mobile-card-value" style={{ color: 'var(--text-primary)' }}>{formatKRW(acc.deposit_krw)}</span>
                        </div>
                        {(Number(acc.deposit_usd) > 0 || currencyMode === 'USD') && (
                          <div className="mobile-card-row" style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid var(--border-color)' }}>
                            <span style={{ fontWeight: 700 }}>💵 외화 예수금 (USD)</span>
                            <span className="mobile-card-value" style={{ color: 'var(--accent-primary)' }}>{formatUSD(acc.deposit_usd)}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })
      )}
      </div>
    </>
  );
}
