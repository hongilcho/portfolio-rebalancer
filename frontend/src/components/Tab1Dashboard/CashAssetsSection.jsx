/** CashAssetsSection: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { formatKRW, formatUSD } from '../../utils/formatters';

export default function CashAssetsSection({ cash_assets }) {
  return (
    <>
      {/* 3. Cash Assets Section */}
      <div className="section-card">
        <div className="section-title">
          <span>💵 현금성 자산 (예수금)</span>
        </div>

        {/* Desktop Table */}
        <div className="desktop-view">
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>구분</th>
                  <th>보유 외화 수량</th>
                  <th>원화 환산 평가금액(원)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600 }}>💵 원화 현금 (KRW)</td>
                  <td>-</td>
                  <td>{formatKRW(cash_assets?.krw_cash)}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>💵 달러 현금 (USD)</td>
                  <td>{formatUSD(cash_assets?.usd_cash)}</td>
                  <td>{formatKRW(cash_assets?.usd_cash_krw)}</td>
                </tr>
                <tr className="total-row">
                  <td>총합계</td>
                  <td>-</td>
                  <td>{formatKRW(cash_assets?.total_cash_krw)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Mobile Cards */}
        <div className="mobile-view">
          <div className="mobile-card-item">
            <div className="mobile-card-row">
              <span style={{ fontWeight: 600 }}>💵 원화 현금 (KRW)</span>
              <span style={{ fontWeight: 700 }}>{formatKRW(cash_assets?.krw_cash)}</span>
            </div>
            <div className="mobile-card-row" style={{ marginTop: '8px' }}>
              <span style={{ fontWeight: 600 }}>💵 달러 현금 (USD)</span>
              <span style={{ fontWeight: 700 }}>
                {formatUSD(cash_assets?.usd_cash)} <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>({formatKRW(cash_assets?.usd_cash_krw)})</span>
              </span>
            </div>
            <div className="mobile-card-row" style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-color)' }}>
              <span style={{ fontWeight: 700 }}>총 현금 합계</span>
              <span style={{ fontWeight: 800, fontSize: '1.05rem', color: 'var(--accent-primary)' }}>{formatKRW(cash_assets?.total_cash_krw)}</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
