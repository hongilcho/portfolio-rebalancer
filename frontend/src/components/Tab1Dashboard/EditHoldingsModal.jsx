/**
 * 계좌별 예수금 및 보유 종목 수량/평단가 직접 편집 모달 (EditHoldingsModal.jsx)
 * ==============================================================================
 * 대시보드에서 계좌를 선택하여 원화/외화 예수금과 각 종목의 보유 수량 및 매입 평단가를 수동 입력/수정합니다.
 */

import React, { useState, useEffect } from 'react';
import { api } from '../../utils/api';
import { formatKRW, formatUSD } from '../../utils/formatters';
import KoreanNumberInput from '../common/KoreanNumberInput';

export default function EditHoldingsModal({ 
  accounts, 
  assets, 
  onClose, 
  onSaved,
  usdKrw = 1350
}) {
  const [selectedAccId, setSelectedAccId] = useState(accounts[0]?.id || '');
  const [depositKrw, setDepositKrw] = useState(0);
  const [depositUsd, setDepositUsd] = useState(0);
  const [holdingsInputs, setHoldingsInputs] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const effectiveRate = Number(usdKrw) > 0 ? Number(usdKrw) : 1350;
  const selectedAcc = accounts.find((a) => String(a.id) === String(selectedAccId));

  // Load account data when selected account changes
  useEffect(() => {
    const acc = accounts.find((a) => String(a.id) === String(selectedAccId));
    if (!acc) return;
    setDepositKrw(Number(acc.deposit_krw || 0));
    setDepositUsd(Number(acc.deposit_usd || 0));

    // Load holdings
    setLoading(true);
    api.getAccountHoldings(acc.id)
      .then((res) => {
        const map = {};
        (res.holdings || []).forEach((h) => {
          const isUs = h.market === 'US';
          const avgKrw = Number(h.avg_price || 0);
          let avgUsd = Number(h.avg_price_usd || 0);
          if (isUs && avgUsd <= 0 && avgKrw > 0 && effectiveRate > 0) {
            avgUsd = Math.round((avgKrw / effectiveRate) * 100) / 100;
          }
          map[String(h.asset_id)] = {
            quantity: Number(h.quantity || 0),
            avg_price: avgKrw,
            avg_price_usd: avgUsd
          };
        });
        setHoldingsInputs(map);
      })
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [selectedAccId, accounts, effectiveRate]);

  // Filter allowed assets for this account
  const allowedAssets = assets.filter((ast) => 
    (ast.allowed_accounts || []).map(String).includes(String(selectedAccId))
  );

  const handleQtyChange = (assetId, qty) => {
    setHoldingsInputs((prev) => ({
      ...prev,
      [assetId]: {
        ...prev[assetId],
        quantity: qty
      }
    }));
  };

  const handleAvgPriceUsdChange = (assetId, priceUsd) => {
    const numUsd = parseFloat(priceUsd) || 0;
    const computedKrw = Math.round(numUsd * effectiveRate);
    setHoldingsInputs((prev) => ({
      ...prev,
      [assetId]: {
        ...prev[assetId],
        avg_price_usd: numUsd,
        avg_price: computedKrw
      }
    }));
  };

  const handleAvgPriceKrwChange = (assetId, priceKrw, isUs = false) => {
    const numKrw = parseFloat(priceKrw) || 0;
    setHoldingsInputs((prev) => ({
      ...prev,
      [assetId]: {
        ...prev[assetId],
        avg_price: numKrw,
        avg_price_usd: isUs && effectiveRate > 0 ? Math.round((numKrw / effectiveRate) * 100) / 100 : (prev[assetId]?.avg_price_usd || 0)
      }
    }));
  };

  const handleSave = async () => {
    if (!selectedAcc) return;
    setSaving(true);
    try {
      const holdingsPayload = allowedAssets.map((ast) => {
        const current = holdingsInputs[String(ast.id)] || { quantity: 0, avg_price: 0, avg_price_usd: 0 };
        return {
          asset_id: String(ast.id),
          quantity: Number(current.quantity || 0),
          avg_price: Number(current.avg_price || 0),
          avg_price_usd: Number(current.avg_price_usd || 0)
        };
      });

      await api.saveHoldings({
        account_id: String(selectedAcc.id),
        deposit_krw: Number(depositKrw),
        deposit_usd: Number(depositUsd),
        holdings: holdingsPayload
      });

      alert('예수금 및 보유 수량/평단가가 성공적으로 저장되었습니다.');
      onSaved();
      onClose();
    } catch (err) {
      alert(`저장 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '680px' }}>
        <div className="modal-header">
          <h3 className="modal-title">✏️ 보유 잔고 및 예수금 입력/수정</h3>
          <button className="btn btn-sm btn-secondary" onClick={onClose}>✕</button>
        </div>

        {/* Account Selector */}
        <div className="form-group">
          <label className="form-label">수정할 계좌 선택</label>
          <select 
            className="input-select"
            value={selectedAccId}
            onChange={(e) => setSelectedAccId(e.target.value)}
          >
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                [{acc.account_type}] {acc.account_alias} ({acc.account_no})
              </option>
            ))}
          </select>
        </div>

        {/* Deposits Input */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
          <KoreanNumberInput
            label="원화 예수금 (원)"
            value={depositKrw}
            onChange={setDepositKrw}
            step={10000}
          />
          <div className="form-group">
            <label className="form-label">
              외화 예수금 ($ USD) {depositUsd > 0 && <span className="helper-text">({formatUSD(depositUsd)})</span>}
            </label>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', fontWeight: 700, color: 'var(--accent-primary)' }}>$</span>
              <input
                type="number"
                className="input-number"
                style={{ paddingLeft: '24px' }}
                value={depositUsd}
                onChange={(e) => setDepositUsd(parseFloat(e.target.value) || 0)}
                step={10}
                min={0}
              />
            </div>
            {depositUsd > 0 && (
              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                ≈ {formatKRW(Math.round(depositUsd * effectiveRate))} (환율 {effectiveRate.toLocaleString()}원)
              </div>
            )}
          </div>
        </div>

        {/* Allowed Assets Holdings */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '8px' }}>
          <h4 style={{ fontSize: '0.96rem', fontWeight: 700, margin: 0 }}>
            📦 이 계좌에서 운용 가능한 종목 수량 및 평단가
          </h4>
          <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
            적용 환율: $1 = {effectiveRate.toLocaleString()}원
          </span>
        </div>

        {loading ? (
          <p style={{ color: 'var(--text-secondary)', padding: '20px 0' }}>잔고 로딩 중...</p>
        ) : allowedAssets.length === 0 ? (
          <div className="alert-banner alert-info">
            이 계좌에 운용 가능하도록 매핑된 자산이 없습니다. [2. 목표 비중 설정] 탭에서 먼저 계좌를 연결해 주세요.
          </div>
        ) : (
          <div style={{ maxHeight: '380px', overflowY: 'auto', paddingRight: '6px' }}>
            {allowedAssets.map((ast) => {
              const h = holdingsInputs[String(ast.id)] || { quantity: 0, avg_price: 0, avg_price_usd: 0 };
              const isUs = ast.market === 'US';
              const isGold = ast.name.includes('금') || ast.ticker === 'M04020000';
              const unit = isGold ? 'g' : '주';

              return (
                <div key={ast.id} style={{ background: 'var(--bg-card-subtle)', padding: '14px', borderRadius: 'var(--radius-md)', marginBottom: '12px', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <div style={{ fontWeight: 700 }}>
                      {ast.name} 
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginLeft: '6px' }}>
                        ({ast.ticker})
                      </span>
                      {isUs && (
                        <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '1px 6px' }}>
                          🇺🇸 미국상장 (USD)
                        </span>
                      )}
                    </div>
                    <span className={`badge ${ast.is_risk_asset ? 'badge-risk' : 'badge-safe'}`}>
                      {ast.is_risk_asset ? '🔴 위험자산' : '🟢 안전자산'}
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    {/* 1. 수량 입력 */}
                    <div className="form-group" style={{ margin: 0 }}>
                      <label className="form-label" style={{ fontSize: '0.78rem' }}>
                        보유 수량 <span className="helper-text">({h.quantity} {unit})</span>
                      </label>
                      <input
                        type="number"
                        className="input-number"
                        value={h.quantity}
                        onChange={(e) => handleQtyChange(String(ast.id), parseFloat(e.target.value) || 0)}
                        step={1}
                        min={0}
                      />
                    </div>

                    {/* 2. 평단가 입력: 미국 상장 자산은 USD($) 직접 입력, 국내 자산은 KRW(원) 입력 */}
                    {isUs ? (
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: '0.78rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span>평균 매입단가 ($ USD)</span>
                          <span className="badge badge-accent" style={{ fontSize: '0.68rem', padding: '1px 5px' }}>
                            달러 직접입력
                          </span>
                        </label>
                        <div style={{ position: 'relative' }}>
                          <span style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', fontWeight: 700, color: 'var(--accent-primary)' }}>$</span>
                          <input
                            type="number"
                            className="input-number"
                            style={{ paddingLeft: '24px', fontWeight: 700 }}
                            value={h.avg_price_usd !== undefined && h.avg_price_usd !== null ? h.avg_price_usd : ''}
                            placeholder="0.00"
                            onChange={(e) => handleAvgPriceUsdChange(String(ast.id), e.target.value)}
                            step={0.01}
                            min={0}
                          />
                        </div>
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                          ≈ {formatKRW(h.avg_price)} <span style={{ opacity: 0.8 }}>(환율 {effectiveRate.toLocaleString()}원 적용)</span>
                        </div>
                      </div>
                    ) : (
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: '0.78rem' }}>
                          평균 매입가 (원화) <span className="helper-text">({formatKRW(h.avg_price)})</span>
                        </label>
                        <input
                          type="number"
                          className="input-number"
                          value={h.avg_price}
                          onChange={(e) => handleAvgPriceKrwChange(String(ast.id), parseFloat(e.target.value) || 0)}
                          step={100}
                          min={0}
                        />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div style={{ display: 'flex', gap: '10px', marginTop: '24px' }}>
          <button 
            className="btn btn-primary btn-block" 
            onClick={handleSave} 
            disabled={saving}
          >
            {saving ? '저장 중...' : '💾 예수금 및 보유 수량/평단가 저장'}
          </button>
        </div>
      </div>
    </div>
  );
}

