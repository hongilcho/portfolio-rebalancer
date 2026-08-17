import React, { useState } from 'react';
import { 
  DollarSign, TrendingUp, AlertTriangle, CheckCircle2, 
  ChevronDown, ChevronUp, Edit2, RefreshCw, Layers 
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
  const [syncingApi, setSyncingApi] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  if (!dashboardData) {
    return <div className="section-card">대시보드 데이터를 불러오는 중입니다...</div>;
  }

  const { kpi, stock_assets, cash_assets, accounts: accSummaries, drift_scale_max } = dashboardData;

  const toggleAccordion = (accId) => {
    setExpandedAccs((prev) => ({
      ...prev,
      [accId]: prev[accId] === undefined ? false : !prev[accId]
    }));
  };

  const handleSyncNamuh = async () => {
    setSyncingApi(true);
    setSyncResult(null);
    try {
      const res = await api.syncNamuh();
      setSyncResult(res);
      onRefresh();
    } catch (err) {
      setSyncResult({ success: false, message: err.message, errors: [err.message] });
    } finally {
      setSyncingApi(false);
    }
  };

  const isProfit = (kpi?.total_stock_profit || 0) >= 0;

  return (
    <div>
      {/* 1. Top KPI Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-title">💵 총 매입 금액 (투자 원금)</div>
          <div className="kpi-value">{formatKRW(kpi?.total_stock_buy)}</div>
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

      {/* 2. Stock Assets Tables Section */}
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

      {/* 3. Cash Assets Section */}
      <div className="section-card">
        <div className="section-title">
          <span>💵 현금성 자산 (예수금)</span>
        </div>
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

      {/* 4. Accounts Cards Section */}
      <div className="section-card">
        <div className="section-title">
          <span>💳 계좌별 자산 현황 & 한도 모니터링</span>
        </div>

        {accSummaries?.map((acc) => {
          const isExpanded = expandedAccs[acc.id] !== false; // default expanded
          const isIrp = acc.account_type === 'IRP';
          const isIrpOverRisk = isIrp && acc.risk_pct > 70.0;
          const isAccProfit = acc.profit_krw >= 0;

          return (
            <div key={acc.id} className="account-accordion">
              <div className="accordion-header" onClick={() => toggleAccordion(acc.id)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Layers size={18} color="var(--accent-primary)" />
                  <span style={{ fontWeight: 700, fontSize: '1rem' }}>
                    [{acc.account_type}] {acc.account_alias} ({acc.account_no})
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <span style={{ fontWeight: 800, fontSize: '1.05rem' }}>
                    총 {formatKRW(acc.total_val)}
                  </span>
                  {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </div>
              </div>

              {isExpanded && (
                <div className="accordion-body">
                  {/* Account Summary Stats */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '20px', marginBottom: '16px', background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: 'var(--radius-md)' }}>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>주식 평가금액</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>{formatKRW(acc.stock_eval)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>평가 손익 / 수익률</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: isAccProfit ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                        {isAccProfit ? '+' : ''}{formatKRW(acc.profit_krw)} ({formatPercent(acc.profit_pct)})
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>보유 예수금</div>
                      <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        원화 {formatKRW(acc.deposit_krw)} | 달러 {formatUSD(acc.deposit_usd)}
                      </div>
                    </div>
                  </div>

                  {/* IRP Risk Asset Warning / Status */}
                  {isIrp && (
                    <div className={`alert-banner ${isIrpOverRisk ? 'alert-danger' : 'alert-success'}`}>
                      {isIrpOverRisk ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
                      <span>
                        {isIrpOverRisk
                          ? `🚨 [IRP 규제 경고] 위험자산 비중이 ${acc.risk_pct.toFixed(1)}%로 최대 한도(70%)를 초과했습니다! 신규 매수가 제한될 수 있습니다.`
                          : `✅ [IRP 규제 준수] 위험자산 비중 ${acc.risk_pct.toFixed(1)}% (70% 한도 이내 준수 중)`}
                      </span>
                    </div>
                  )}

                  {/* Annual Contribution Limit Bar */}
                  {acc.annual_limit > 0 && (
                    <div className="progress-bar-container">
                      <div className="progress-bar-label">
                        <span>📅 <strong>연간 납입 한도</strong>: {formatKRW(acc.annual_limit)} 중 약 {formatKRW(acc.principal_val)} 소진</span>
                        <span>{(acc.annual_limit_pct * 100).toFixed(1)}%</span>
                      </div>
                      <div className="progress-track">
                        <div className="progress-fill" style={{ width: `${acc.annual_limit_pct * 100}%` }} />
                      </div>
                    </div>
                  )}

                  {/* Tax Deduction Limit Bar */}
                  {acc.tax_limit > 0 && (
                    <div className="progress-bar-container">
                      <div className="progress-bar-label">
                        <span>💡 <strong>세액공제 최대 한도</strong>: {formatKRW(acc.tax_limit)} 중 약 {formatKRW(acc.principal_val)} 채움</span>
                        <span>{(acc.tax_limit_pct * 100).toFixed(1)}%</span>
                      </div>
                      <div className="progress-track">
                        <div className="progress-fill" style={{ width: `${acc.tax_limit_pct * 100}%`, background: '#10B981' }} />
                      </div>
                    </div>
                  )}

                  {/* Account Holdings Table */}
                  <h5 style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-secondary)', marginTop: '16px', marginBottom: '8px' }}>
                    📦 보유 종목 목록
                  </h5>
                  {acc.holdings && acc.holdings.length > 0 ? (
                    <div className="table-container">
                      <table className="custom-table">
                        <thead>
                          <tr>
                            <th>종목명</th>
                            <th>보유수량</th>
                            <th>손익</th>
                            <th>평가금액</th>
                            <th>평단가</th>
                            <th>현재가</th>
                            <th>위험구분</th>
                          </tr>
                        </thead>
                        <tbody>
                          {acc.holdings.map((h) => {
                            const isHProfit = h.profit_krw >= 0;
                            return (
                              <tr key={h.asset_id}>
                                <td style={{ fontWeight: 600 }}>{h.asset_name}</td>
                                <td>{formatQuantity(h.quantity, h.unit)}</td>
                                <td style={{ color: isHProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                                  {isHProfit ? '+' : ''}{formatKRW(h.profit_krw)} ({formatPercent(h.profit_pct)})
                                </td>
                                <td>{formatKRW(h.eval_amount)}</td>
                                <td>{formatKRW(h.avg_price)}</td>
                                <td>{formatKRW(h.current_price)}</td>
                                <td>
                                  <span className={`badge ${h.is_risk_asset ? 'badge-risk' : 'badge-safe'}`}>
                                    {h.is_risk_asset ? '🔴 위험' : '🟢 안전'}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: '8px 0' }}>
                      등록된 보유 주식이 없습니다.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 5. Namuh API Sync Button */}
      <div className="section-card" style={{ textAlign: 'center', background: 'rgba(99, 102, 241, 0.05)' }}>
        <button 
          className="btn btn-primary"
          style={{ padding: '12px 24px', fontSize: '1rem' }}
          onClick={handleSyncNamuh}
          disabled={syncingApi}
        >
          <RefreshCw size={18} className={syncingApi ? 'animate-spin' : ''} />
          {syncingApi ? '증권사 API 통신 중...' : '🔄 Namuh 증권 API로 일반계좌(ISA/IRP/연금제외) 갱신하기'}
        </button>

        {syncResult && (
          <div style={{ marginTop: '16px', textAlign: 'left', maxWidth: '600px', margin: '16px auto 0 auto' }}>
            <div className={`alert-banner ${syncResult.success ? 'alert-success' : 'alert-danger'}`}>
              <span>{syncResult.message}</span>
            </div>
            {syncResult.errors && syncResult.errors.length > 0 && (
              <div style={{ fontSize: '0.85rem', color: 'var(--color-risk)' }}>
                {syncResult.errors.map((e, idx) => <div key={idx}>⚠️ {e}</div>)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Edit Holdings Modal */}
      {isEditModalOpen && (
        <EditHoldingsModal
          accounts={accounts}
          assets={assets}
          onClose={() => setIsEditModalOpen(false)}
          onSaved={onRefresh}
        />
      )}
    </div>
  );
}
