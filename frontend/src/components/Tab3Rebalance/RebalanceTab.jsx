import React, { useState } from 'react';
import { Play, ArrowRightLeft, DollarSign, Trash2, CheckCircle2, AlertCircle } from 'lucide-react';
import { api } from '../../utils/api';
import { formatKRW, formatQuantity, formatPercent, numToKrMixed } from '../../utils/formatters';
import KoreanNumberInput from '../common/KoreanNumberInput';
import DriftBar from '../common/DriftBar';

export default function RebalanceTab({ onRefresh }) {
  const [scenario, setScenario] = useState('NEW_CASH');
  const [newCash, setNewCash] = useState(0);
  const [driftThreshold, setDriftThreshold] = useState(5.0);
  const [calculating, setCalculating] = useState(false);
  const [result, setResult] = useState(null);
  const [applyingTransfer, setApplyingTransfer] = useState(false);

  const handleCalculate = async () => {
    setCalculating(true);
    setResult(null);
    try {
      const res = await api.calculateRebalance({
        scenario,
        new_cash_krw: Number(newCash),
        drift_threshold: Number(driftThreshold)
      });
      setResult(res);
    } catch (err) {
      setResult({ success: false, message: err.message });
    } finally {
      setCalculating(false);
    }
  };

  const handleApplyTransfers = async () => {
    if (!result?.transfer_plan || result.transfer_plan.length === 0) return;
    setApplyingTransfer(true);
    try {
      const res = await api.applyTransfers(result.transfer_plan);
      alert(res.message || '이체 지시서가 실제 계좌 예수금에 반영되었습니다.');
      onRefresh();
    } catch (err) {
      alert(`이체 반영 실패: ${err.message}`);
    } finally {
      setApplyingTransfer(false);
    }
  };

  return (
    <div>
      {/* 1. Configuration Card */}
      <div className="section-card">
        <div className="section-title">
          <span>⚖️ 리밸런싱 전략 수립</span>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '20px' }}>
          현재 자산 상태와 목표 비중을 바탕으로 <strong>구체적인 매매 및 계좌 간 자금 이체 지시서</strong>를 생성합니다.
        </p>

        {/* Scenario Selection */}
        <div className="form-group" style={{ marginBottom: '20px' }}>
          <label className="form-label">리밸런싱 시나리오 선택</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div 
              onClick={() => setScenario('NEW_CASH')}
              style={{
                padding: '16px',
                borderRadius: 'var(--radius-md)',
                cursor: 'pointer',
                border: scenario === 'NEW_CASH' ? '2px solid var(--accent-primary)' : '1px solid var(--border-color)',
                background: scenario === 'NEW_CASH' ? 'rgba(99, 102, 241, 0.15)' : 'var(--bg-card-subtle)',
                transition: 'all 0.15s ease'
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: '4px' }}>💰 신규 자금 투입</div>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                기존 자산을 매도하지 않고, 새로 넣는 현금만으로 목표 비중에 최대한 가깝게 매수합니다.
              </div>
            </div>

            <div 
              onClick={() => setScenario('DRIFT')}
              style={{
                padding: '16px',
                borderRadius: 'var(--radius-md)',
                cursor: 'pointer',
                border: scenario === 'DRIFT' ? '2px solid var(--accent-primary)' : '1px solid var(--border-color)',
                background: scenario === 'DRIFT' ? 'rgba(99, 102, 241, 0.15)' : 'var(--bg-card-subtle)',
                transition: 'all 0.15s ease'
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: '4px' }}>📉 괴리율 기반 리밸런싱</div>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                설정한 허용 괴리율을 초과한 자산에 대해 초과분은 매도하고 부족분은 매수합니다.
              </div>
            </div>
          </div>
        </div>

        {/* Condition Inputs */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
          <KoreanNumberInput
            label="신규 투입 현금액"
            value={newCash}
            onChange={setNewCash}
            step={100000}
          />

          <div className="form-group">
            <label className="form-label">
              허용 괴리율 (%) {scenario === 'NEW_CASH' && <span style={{ color: 'var(--text-muted)' }}>(신규투입 모드에서는 비활성화)</span>}
            </label>
            <input
              type="number"
              step="0.5"
              min="0"
              className="input-number"
              value={driftThreshold}
              onChange={(e) => setDriftThreshold(parseFloat(e.target.value) || 0)}
              disabled={scenario === 'NEW_CASH'}
            />
          </div>
        </div>

        {/* Calculate Button */}
        <button 
          className="btn btn-primary btn-block"
          style={{ padding: '14px', fontSize: '1rem' }}
          onClick={handleCalculate}
          disabled={calculating}
        >
          <Play size={18} />
          {calculating ? '최적 매매 경로 계산 중...' : '🚀 리밸런싱 전략 계산하기'}
        </button>
      </div>

      {/* 2. Calculation Results Section */}
      {result && (
        <div className="section-card">
          <div className="section-title">
            <span>📋 리밸런싱 실행 지시서</span>
            <button 
              className="btn btn-secondary btn-sm"
              onClick={() => setResult(null)}
            >
              <Trash2 size={14} /> 계산 결과 지우기
            </button>
          </div>

          {!result.success ? (
            <div className="alert-banner alert-danger">
              <AlertCircle size={18} />
              <span>{result.message}</span>
            </div>
          ) : result.trade_plan?.length === 0 && result.transfer_plan?.length === 0 ? (
            <div className="alert-banner alert-success">
              <CheckCircle2 size={18} />
              <span>{result.message}</span>
            </div>
          ) : (
            <div>
              {/* 1️⃣ Cash Transfer Plan */}
              <div style={{ marginBottom: '28px' }}>
                <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ArrowRightLeft size={18} color="var(--accent-primary)" />
                  1️⃣ 자금 이체 지시서
                </h4>

                {result.transfer_plan && result.transfer_plan.length > 0 ? (
                  <div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
                      {result.transfer_plan.map((tr, idx) => (
                        <div 
                          key={idx}
                          className={`alert-banner ${tr.type === 'DEPOSIT' ? 'alert-info' : 'alert-success'}`}
                          style={{ margin: 0 }}
                        >
                          <span>{tr.type === 'DEPOSIT' ? '📥' : '✔️'} {tr.msg}</span>
                        </div>
                      ))}
                    </div>

                    <button 
                      className="btn btn-primary"
                      onClick={handleApplyTransfers}
                      disabled={applyingTransfer}
                      style={{ background: '#10B981', borderColor: '#10B981' }}
                    >
                      <DollarSign size={16} />
                      {applyingTransfer ? '예수금 반영 중...' : '💰 위 이체 지시서를 실제 계좌 예수금에 바로 반영하기'}
                    </button>
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                    필요한 자금 이체가 없습니다.
                  </p>
                )}
              </div>

              {/* 2️⃣ Trade Orders Plan */}
              <div style={{ marginBottom: '28px' }}>
                <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  📊 2️⃣ 매매 지시서
                </h4>

                {result.trade_plan && result.trade_plan.length > 0 ? (
                  <div className="table-container">
                    <table className="custom-table">
                      <thead>
                        <tr>
                          <th>계좌</th>
                          <th>종류</th>
                          <th>자산명</th>
                          <th>수량</th>
                          <th>예상 체결가</th>
                          <th>총액</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trade_plan.map((t, idx) => {
                          const isBuy = t.type === 'BUY';
                          return (
                            <tr key={idx}>
                              <td style={{ fontWeight: 600 }}>{t.account_alias}</td>
                              <td>
                                <span className={`badge ${isBuy ? 'badge-profit' : 'badge-loss'}`} style={{ fontSize: '0.82rem' }}>
                                  {isBuy ? '🔵 매수' : '🔴 매도'}
                                </span>
                              </td>
                              <td style={{ fontWeight: 600 }}>{t.asset_name}</td>
                              <td>{formatQuantity(t.qty)}</td>
                              <td>{formatKRW(t.price)}</td>
                              <td style={{ fontWeight: 700 }}>{formatKRW(t.total_krw)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                    필요한 매매가 없습니다.
                  </p>
                )}
              </div>

              {/* 3️⃣ Projected Simulation Table */}
              <div>
                <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px' }}>
                  📈 3️⃣ 리밸런싱 후 예상 포트폴리오 비중
                </h4>

                <div className="table-container">
                  <table className="custom-table">
                    <thead>
                      <tr>
                        <th>자산명</th>
                        <th>최종 수량</th>
                        <th>예상 평가액</th>
                        <th style={{ textAlign: 'center' }}>목표 비중(%)</th>
                        <th style={{ textAlign: 'center' }}>예상 비중(%)</th>
                        <th style={{ textAlign: 'center', width: '220px' }}>괴리율(%)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.simulated_assets?.map((s) => {
                        const finalQty = s.current_qty + s.qty_diff;
                        const hasDiff = s.qty_diff !== 0;
                        const isPlus = s.qty_diff > 0;

                        return (
                          <tr key={s.asset_id}>
                            <td style={{ fontWeight: 600 }}>{s.asset_name}</td>
                            <td>
                              {formatQuantity(finalQty)}{' '}
                              {hasDiff && (
                                <span style={{ color: isPlus ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                                  ({isPlus ? '+' : ''}{s.qty_diff.toFixed(0)})
                                </span>
                              )}
                            </td>
                            <td>{formatKRW(s.projected_val)}</td>
                            <td style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>{s.target_weight.toFixed(1)}%</td>
                            <td style={{ textAlign: 'center', fontWeight: 700 }}>{s.projected_weight.toFixed(1)}%</td>
                            <td>
                              <DriftBar drift={s.drift} scaleMax={result.scale_max} />
                            </td>
                          </tr>
                        );
                      })}
                      {/* Total Row */}
                      <tr className="total-row">
                        <td>총합</td>
                        <td>-</td>
                        <td>{formatKRW(result.total_sim)}</td>
                        <td style={{ textAlign: 'center' }}>100.0%</td>
                        <td style={{ textAlign: 'center' }}>100.0%</td>
                        <td>-</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
