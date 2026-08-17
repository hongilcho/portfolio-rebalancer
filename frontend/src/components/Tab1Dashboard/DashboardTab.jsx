import React, { useState } from 'react';
import { 
  TrendingUp, TrendingDown, DollarSign, Wallet, ShieldAlert, 
  ChevronDown, ChevronUp, Edit2, RefreshCw 
} from 'lucide-react';
import { formatKRW, formatUSD, formatQuantity, formatPercent } from '../../utils/formatters';
import DriftBar from '../common/DriftBar';
import EditHoldingsModal from './EditHoldingsModal';
import { api } from '../../utils/api';

export default function DashboardTab({ 
  dashboardData, 
  assets, 
  accounts, 
  onRefresh 
}) {
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [expandedAccs, setExpandedAccs] = useState({});
  const [syncingNamuh, setSyncingNamuh] = useState(false);

  if (!dashboardData) {
    return <div className="section-card">데이터를 불러오는 중입니다...</div>;
  }

  const {
    kpi,
    stock_assets,
    cash_assets,
    drift_scale_max,
    account_summaries: accSummaries,
    usd_krw
  } = dashboardData;

  const isProfit = (kpi?.total_stock_profit || 0) >= 0;

  const toggleAccordion = (accId) => {
    setExpandedAccs((prev) => ({
      ...prev,
      [accId]: !prev[accId]
    }));
  };

  const handleSyncNamuh = async () => {
    setSyncingNamuh(true);
    try {
      const res = await api.syncNamuh();
      alert(res.message || 'NH투자증권 잔고 동기화 완료!');
      onRefresh();
    } catch (err) {
      alert(`동기화 실패: ${err.message}`);
    } finally {
      setSyncingNamuh(false);
    }
  };

  return (
    <div>
      {/* 1. Top KPI Summary Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-title">💰 총 포트폴리오 평가금액 (현금 포함)</div>
          <div className="kpi-value">{formatKRW(kpi?.total_portfolio_eval)}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">📈 총 주식/자산 평가금액 (현금 제외)</div>
          <div className="kpi-value">{formatKRW(kpi?.total_stock_eval)}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">총 평가 손익</div>
          <div className="kpi-value" style={{ color: isProfit ? 'var(--color-profit)' : 'var(--color-loss)' }}>
            {isProfit ? '+' : ''}{formatKRW(kpi?.total_stock_profit)}
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-title">총 수익률</div>
          <div className="kpi-value" style={{ color: isProfit ? 'var(--color-profit)' : 'var(--color-loss)' }}>
            {formatPercent(kpi?.total_stock_return)}
          </div>
        </div>
      </div>

      {/* 2. Stock Assets Section */}
      <div className="section-card">
        <div className="section-title">
          <span>📈 주식 및 금현물 자산 현황</span>
          <button 
            className="btn btn-secondary btn-sm"
            onClick={() => setIsEditModalOpen(true)}
          >
            <Edit2 size={14} /> 보유 잔고/예수금 직접 수정
          </button>
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
                  <th>손익(원)</th>
                  <th>평가금액(원)</th>
                  <th>평단가(원)</th>
                  <th>현재가(원)</th>
                </tr>
              </thead>
              <tbody>
                {stock_assets?.map((item) => {
                  const isItemProfit = item.profit_krw >= 0;
                  return (
                    <tr key={item.asset_id}>
                      <td style={{ fontWeight: 600 }}>{item.name}</td>
                      <td>{formatQuantity(item.quantity, item.unit)}</td>
                      <td style={{ color: isItemProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                        {formatPercent(item.profit_pct)}
                      </td>
                      <td style={{ color: isItemProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                        {isItemProfit ? '+' : ''}{formatKRW(item.profit_krw)}
                      </td>
                      <td style={{ fontWeight: 600 }}>{formatKRW(item.eval_amount)}</td>
                      <td>{formatKRW(item.avg_price)}</td>
                      <td>{formatKRW(item.current_price)}</td>
                    </tr>
                  );
                })}
                {/* Total Row */}
                <tr className="total-row">
                  <td>총합계</td>
                  <td>-</td>
                  <td style={{ color: isProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                    {formatPercent(kpi?.total_stock_return)}
                  </td>
                  <td style={{ color: isProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                    {isProfit ? '+' : ''}{formatKRW(kpi?.total_stock_profit)}
                  </td>
                  <td>{formatKRW(kpi?.total_stock_eval)}</td>
                  <td>-</td>
                  <td>-</td>
                </tr>
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
                {stock_assets?.map((item) => (
                  <tr key={item.asset_id}>
                    <td style={{ fontWeight: 600 }}>{item.name}</td>
                    <td style={{ textAlign: 'center', fontWeight: 600 }}>{item.weight_pct.toFixed(1)}%</td>
                    <td style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>{item.target_weight_pct.toFixed(1)}%</td>
                    <td>
                      <DriftBar drift={item.drift_pct} scaleMax={drift_scale_max} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 📱 MOBILE RESPONSIVE CARDS (Screen <= 768px) */}
        <div className="mobile-view">
          {stock_assets?.map((item) => {
            const isItemProfit = item.profit_krw >= 0;
            return (
              <div key={item.asset_id} className="mobile-card-item">
                {/* Row 1: Name + Eval Amount */}
                <div className="mobile-card-row">
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '1rem' }}>{item.name}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '6px' }}>({item.ticker})</span>
                  </div>
                  <span style={{ fontWeight: 800, fontSize: '1.05rem' }}>{formatKRW(item.eval_amount)}</span>
                </div>

                {/* Row 2: Quantity & Prices + Profit/Loss */}
                <div className="mobile-card-row" style={{ fontSize: '0.86rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {formatQuantity(item.quantity, item.unit)} · 평단 {formatKRW(item.avg_price)}
                  </span>
                  <span style={{ color: isItemProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                    {isItemProfit ? '+' : ''}{formatKRW(item.profit_krw)} ({formatPercent(item.profit_pct)})
                  </span>
                </div>

                {/* Row 3: Weight info & Drift */}
                <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-color)' }}>
                  <div className="mobile-card-row" style={{ fontSize: '0.82rem', marginBottom: '6px' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      현재 비중 <strong>{item.weight_pct.toFixed(1)}%</strong> / 목표 <strong>{item.target_weight_pct.toFixed(1)}%</strong>
                    </span>
                    <span style={{ fontWeight: 700, color: item.drift_pct > 0 ? 'var(--color-profit)' : item.drift_pct < 0 ? 'var(--color-loss)' : 'var(--text-muted)' }}>
                      괴리율: {item.drift_pct > 0 ? '+' : ''}{item.drift_pct.toFixed(1)}%
                    </span>
                  </div>
                  <DriftBar drift={item.drift_pct} scaleMax={drift_scale_max} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

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

      {/* 4. Accounts Cards Section */}
      <div className="section-card">
        <div className="section-title">
          <span>💳 계좌별 자산 현황 & 한도 모니터링</span>
          <button 
            className="btn btn-secondary btn-sm"
            onClick={handleSyncNamuh}
            disabled={syncingNamuh}
            title="NH투자증권 나무 계좌 잔고 일괄 동기화"
          >
            <RefreshCw size={14} className={syncingNamuh ? 'animate-spin' : ''} />
            {syncingNamuh ? '동기화 중...' : '나무 API 잔고 동기화'}
          </button>
        </div>

        {accSummaries?.map((acc) => {
          const isExpanded = expandedAccs[acc.id] !== false; // default expanded
          const isIrp = acc.account_type === 'IRP';
          const isIrpOverRisk = isIrp && acc.risk_pct > 70.0;

          return (
            <div key={acc.id} className="account-accordion">
              <div className="accordion-header" onClick={() => toggleAccordion(acc.id)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, fontSize: '1.05rem' }}>
                    [{acc.account_type}] {acc.account_alias}
                  </span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {acc.account_no}
                  </span>
                  <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: '#818CF8' }}>
                    우선순위: {acc.priority || 99}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>총 평가금액</div>
                    <div style={{ fontWeight: 700, fontSize: '1rem' }}>{formatKRW(acc.total_eval)}</div>
                  </div>
                  {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </div>
              </div>

              {isExpanded && (
                <div className="accordion-body">
                  {/* IRP Risk Banner */}
                  {isIrp && (
                    <div className={`alert-banner ${isIrpOverRisk ? 'alert-danger' : 'alert-success'}`}>
                      <ShieldAlert size={18} />
                      <span>
                        <strong>IRP 위험자산 비중: {acc.risk_pct.toFixed(1)}%</strong> / 70.0% 제한 —{' '}
                        {isIrpOverRisk ? '⚠️ 70% 초과! 안전자산 비중을 늘려주세요.' : '✅ 규정 준수 중'}
                      </span>
                    </div>
                  )}

                  {/* Limits Progress Bars */}
                  {acc.annual_limit > 0 && (
                    <div className="progress-bar-container">
                      <div className="progress-bar-label">
                        <span>연간 납입한도 소진율 ({formatKRW(acc.total_eval)} / {formatKRW(acc.annual_limit)})</span>
                        <strong>{acc.annual_limit_pct.toFixed(1)}%</strong>
                      </div>
                      <div className="progress-track">
                        <div 
                          className="progress-fill" 
                          style={{ 
                            width: `${Math.min(100, acc.annual_limit_pct)}%`,
                            background: acc.annual_limit_pct > 100 ? 'var(--color-risk)' : 'var(--accent-primary)'
                          }} 
                        />
                      </div>
                    </div>
                  )}

                  {acc.tax_limit > 0 && (
                    <div className="progress-bar-container">
                      <div className="progress-bar-label">
                        <span>세액공제 한도 소진율 ({formatKRW(acc.total_eval)} / {formatKRW(acc.tax_limit)})</span>
                        <strong>{acc.tax_limit_pct.toFixed(1)}%</strong>
                      </div>
                      <div className="progress-track">
                        <div 
                          className="progress-fill" 
                          style={{ 
                            width: `${Math.min(100, acc.tax_limit_pct)}%`,
                            background: acc.tax_limit_pct > 100 ? 'var(--color-risk)' : '#10B981'
                          }} 
                        />
                      </div>
                    </div>
                  )}

                  {/* Holdings Summary */}
                  <div style={{ marginTop: '16px' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                      계좌 내 보유 종목 ({acc.holdings?.length || 0}개) & 예수금
                    </div>

                    {/* Desktop Holdings Table */}
                    <div className="desktop-view">
                      <div className="table-container">
                        <table className="custom-table" style={{ fontSize: '0.85rem' }}>
                          <thead>
                            <tr>
                              <th>종목명</th>
                              <th>보유수량</th>
                              <th>평단가</th>
                              <th>현재가</th>
                              <th>평가금액</th>
                              <th>손익(수익률)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {acc.holdings?.map((h) => {
                              const curP = h.current_price_krw || h.price || 0;
                              const evalAmt = h.quantity * curP;
                              const costAmt = h.quantity * (h.avg_price || 0);
                              const pAmt = evalAmt - costAmt;
                              const pPct = costAmt > 0 ? (pAmt / costAmt) * 100 : 0;
                              const isHProfit = pAmt >= 0;

                              return (
                                <tr key={h.asset_id}>
                                  <td style={{ fontWeight: 600 }}>{h.asset_name}</td>
                                  <td>{formatQuantity(h.quantity)}</td>
                                  <td>{formatKRW(h.avg_price)}</td>
                                  <td>{formatKRW(curP)}</td>
                                  <td style={{ fontWeight: 600 }}>{formatKRW(evalAmt)}</td>
                                  <td style={{ color: isHProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 600 }}>
                                    {isHProfit ? '+' : ''}{formatKRW(pAmt)} ({formatPercent(pPct)})
                                  </td>
                                </tr>
                              );
                            })}
                            <tr>
                              <td style={{ fontWeight: 600 }}>💵 원화 예수금</td>
                              <td colSpan={3}>-</td>
                              <td style={{ fontWeight: 700 }}>{formatKRW(acc.deposit_krw)}</td>
                              <td>-</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Mobile Holdings Cards */}
                    <div className="mobile-view">
                      {acc.holdings?.map((h) => {
                        const curP = h.current_price_krw || h.price || 0;
                        const evalAmt = h.quantity * curP;
                        const costAmt = h.quantity * (h.avg_price || 0);
                        const pAmt = evalAmt - costAmt;
                        const pPct = costAmt > 0 ? (pAmt / costAmt) * 100 : 0;
                        const isHProfit = pAmt >= 0;

                        return (
                          <div key={h.asset_id} className="mobile-card-item" style={{ background: 'var(--bg-surface)' }}>
                            <div className="mobile-card-row">
                              <span style={{ fontWeight: 700 }}>{h.asset_name}</span>
                              <span style={{ fontWeight: 700 }}>{formatKRW(evalAmt)}</span>
                            </div>
                            <div className="mobile-card-row" style={{ fontSize: '0.82rem' }}>
                              <span style={{ color: 'var(--text-secondary)' }}>{formatQuantity(h.quantity)} · 평단 {formatKRW(h.avg_price)}</span>
                              <span style={{ color: isHProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 600 }}>
                                {isHProfit ? '+' : ''}{formatKRW(pAmt)} ({formatPercent(pPct)})
                              </span>
                            </div>
                          </div>
                        );
                      })}
                      <div className="mobile-card-item" style={{ background: 'var(--bg-surface)' }}>
                        <div className="mobile-card-row">
                          <span style={{ fontWeight: 600 }}>💵 원화 예수금</span>
                          <span style={{ fontWeight: 700 }}>{formatKRW(acc.deposit_krw)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Edit Holdings Modal */}
      {isEditModalOpen && (
        <EditHoldingsModal
          accounts={accounts}
          assets={assets}
          onClose={() => setIsEditModalOpen(false)}
          onSaved={() => {
            setIsEditModalOpen(false);
            onRefresh();
          }}
        />
      )}
    </div>
  );
}
