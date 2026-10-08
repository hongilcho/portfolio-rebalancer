/**
 * 계좌별 예수금 및 보유 종목 수량/평단가 직접 편집 모달 (EditHoldingsModal.jsx)
 * ==============================================================================
 * 대시보드에서 계좌를 선택하여 원화/외화 예수금과 각 종목의 보유 수량 및 매입 평단가를 수동 입력/수정합니다.
 */

import React, { useState, useEffect } from 'react';
import { api } from '../../utils/api';
import { formatKRW, formatUSD, getProfitColor } from '../../utils/formatters';
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
  const [ledgerStatus,setLedgerStatus]=useState({accountId:'',ready:false,tracked:false,error:''});

  const effectiveRate = Number(usdKrw) > 0 ? Number(usdKrw) : 1350;
  const selectedAcc = accounts.find((a) => String(a.id) === String(selectedAccId));

  const ledgerReady=ledgerStatus.accountId===String(selectedAccId) && ledgerStatus.ready;
  const tracked=ledgerReady && ledgerStatus.tracked;
  useEffect(()=>{
    let cancelled=false;
    setLedgerStatus({accountId:String(selectedAccId),ready:false,tracked:false,error:''});
    const account=accounts.find(a=>String(a.id)===String(selectedAccId));
    if (!account) return;
    api.getUsdLedgers(account.portfolio_id || 'default').then(res=>{
      if(!cancelled)setLedgerStatus({accountId:String(selectedAccId),ready:true,
        tracked:res.ledgers.some(l=>String(l.account_id)===String(selectedAccId)),error:''});
    }).catch(error=>{if(!cancelled)setLedgerStatus({accountId:String(selectedAccId),ready:false,tracked:false,error:error.message});});
    return()=>{cancelled=true;};
  },[selectedAccId,accounts]);

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
        const existingMap = {};
        (res.holdings || []).forEach((h) => {
          existingMap[String(h.asset_id)] = h;
        });

        const map = {};
        const accAllowed = assets.filter((ast) => 
          (ast.allowed_accounts || []).map(String).includes(String(acc.id))
        );

        accAllowed.forEach((ast) => {
          const aid = String(ast.id);
          const h = existingMap[aid] || {};
          const isUs = ast.market === 'US';
          const avgKrw = Number(h.avg_price || 0);
          let avgUsd = Number(h.avg_price_usd || 0);
          let buyFx = Number(h.buy_fx_rate || 0);
          if (isUs) {
            if (buyFx <= 0) {
              buyFx = avgUsd > 0 && avgKrw > 0 ? Math.round((avgKrw / avgUsd) * 100) / 100 : effectiveRate;
            }
            if (avgUsd <= 0 && avgKrw > 0 && buyFx > 0) {
              avgUsd = Math.round((avgKrw / buyFx) * 100) / 100;
            }
          }
          const origKrw = Number(h.original_avg_price > 0 ? h.original_avg_price : avgKrw);
          let origUsd = Number(h.original_avg_price_usd > 0 ? h.original_avg_price_usd : avgUsd);
          if (isUs && origUsd <= 0 && origKrw > 0 && buyFx > 0) {
            origUsd = Math.round((origKrw / buyFx) * 100) / 100;
          }

          map[aid] = {
            quantity: Number(h.quantity || 0),
            avg_price: avgKrw,
            avg_price_usd: avgUsd,
            buy_fx_rate: buyFx,
            original_avg_price: origKrw,
            original_avg_price_usd: origUsd,
            first_buy_date: h.first_buy_date || '',
            cumulative_dividend: Number(h.cumulative_dividend || 0),
            total_dividend_profit: Number(h.total_dividend_profit || 0),
            dividend_count: Number(h.dividend_count || 0),
            is_dividend_cost_deduct: false
          };
        });
        setHoldingsInputs(map);
      })
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [selectedAccId, accounts, effectiveRate, assets]);

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

  const handleFirstBuyDateChange = (assetId, dateStr) => {
    setHoldingsInputs((prev) => ({
      ...prev,
      [assetId]: {
        ...prev[assetId],
        first_buy_date: dateStr
      }
    }));
  };

  const handleAvgPriceUsdChange = (assetId, priceUsd) => {
    const numUsd = parseFloat(priceUsd) || 0;
    const currentBuyFx = Number(holdingsInputs[assetId]?.buy_fx_rate) || effectiveRate;
    const computedKrw = Math.round(numUsd * currentBuyFx);
    setHoldingsInputs((prev) => ({
      ...prev,
      [assetId]: {
        ...prev[assetId],
        avg_price_usd: numUsd,
        avg_price: computedKrw,
        original_avg_price_usd: numUsd,
        original_avg_price: computedKrw,
        buy_fx_rate: currentBuyFx
      }
    }));
  };

  const handleBuyFxRateChange = (assetId, fxRate) => {
    const numFx = parseFloat(fxRate) || 0;
    const currentUsd = Number(holdingsInputs[assetId]?.avg_price_usd) || 0;
    const computedKrw = Math.round(currentUsd * numFx);
    setHoldingsInputs((prev) => ({
      ...prev,
      [assetId]: {
        ...prev[assetId],
        buy_fx_rate: numFx,
        avg_price: computedKrw,
        original_avg_price: computedKrw
      }
    }));
  };

  const handleAvgPriceKrwChange = (assetId, priceKrw, isUs = false) => {
    const numKrw = parseFloat(priceKrw) || 0;
    const currentBuyFx = Number(holdingsInputs[assetId]?.buy_fx_rate) || effectiveRate;
    const numUsd = isUs && currentBuyFx > 0 ? Math.round((numKrw / currentBuyFx) * 100) / 100 : (holdingsInputs[assetId]?.avg_price_usd || 0);
    setHoldingsInputs((prev) => ({
      ...prev,
      [assetId]: {
        ...prev[assetId],
        avg_price: numKrw,
        original_avg_price: numKrw,
        avg_price_usd: numUsd,
        original_avg_price_usd: numUsd
      }
    }));
  };

  const handleSave = async () => {
    if (!selectedAcc || !ledgerReady) return;
    setSaving(true);
    try {
      if (tracked) {
        await api.commitNhNotices(selectedAcc.portfolio_id || 'default',{
          request_id:crypto.randomUUID(),confirmed:true,
          expected_cash:{[String(selectedAcc.id)]:{deposit_krw:Number(selectedAcc.deposit_krw || 0),deposit_usd:Number(selectedAcc.deposit_usd || 0)}},
          rows:[{kind:'KRW_ADJUST',account_id:String(selectedAcc.id),event_date:new Date(Date.now()+9*3600000).toISOString().slice(0,10),krw_amount:Number(depositKrw)}],
        });
        alert('원화 예수금을 저장했습니다. 달러 잔고·취득원가·종목 원가는 유지했습니다.');
        onSaved();onClose();return;
      }
      const holdingsPayload = allowedAssets.map((ast) => {
        const current = holdingsInputs[String(ast.id)] || { quantity: 0, avg_price: 0, avg_price_usd: 0, buy_fx_rate: 0 };
        return {
          asset_id: String(ast.id),
          quantity: Number(current.quantity || 0),
          avg_price: Number(current.avg_price || 0),
          avg_price_usd: Number(current.avg_price_usd || 0),
          buy_fx_rate: Number(current.buy_fx_rate || 0),
          original_avg_price: Number(current.original_avg_price ?? current.avg_price ?? 0),
          original_avg_price_usd: Number(current.original_avg_price_usd ?? current.avg_price_usd ?? 0),
          first_buy_date: current.first_buy_date || '',
          is_dividend_cost_deduct: Boolean(current.is_dividend_cost_deduct)
        };
      });

      await api.saveHoldings({
        account_id: String(selectedAcc.id),
        deposit_krw: Number(depositKrw),
        deposit_usd: Number(depositUsd),
        holdings: holdingsPayload
      });

      alert('예수금 및 보유 수량/평단가/매입환율이 성공적으로 저장되었습니다.');
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

        {ledgerStatus.error && <p role="alert">달러 추적 상태 조회 실패: {ledgerStatus.error}</p>}
        {tracked && <p>이 계좌는 원화 예수금만 저장합니다. 달러 잔고·보유 원가는 매매·환전 기록으로 관리하세요. 외부 입금은 4번 탭의 NH 알림 가져오기를 사용하면 입금 기록과 예수금을 함께 반영할 수 있습니다.</p>}
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
                disabled={tracked || !ledgerReady}
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

        <fieldset disabled={tracked || !ledgerReady} style={{border:0,padding:0}}>
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
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
                    <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '6px' }}>
                      <span>{ast.name}</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                        ({ast.ticker})
                      </span>
                      {isUs && (
                        <span className="badge badge-accent" style={{ fontSize: '0.72rem', padding: '1px 6px' }}>
                          🇺🇸 미국상장 (USD)
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className={`badge ${ast.is_risk_asset ? 'badge-risk' : 'badge-safe'}`}>
                        {ast.is_risk_asset ? '🔴 위험자산' : '🟢 안전자산'}
                      </span>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: isUs ? 'repeat(auto-fit, minmax(160px, 1fr))' : '1fr 1fr', gap: '12px' }}>
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

                    {/* 2. 평단가 입력: 미국 상장 자산은 USD($) 및 매입환율(원) 입력, 국내 자산은 KRW(원) 입력 */}
                    {isUs ? (
                      <>
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
                        </div>

                        <div className="form-group" style={{ margin: 0 }}>
                          <label className="form-label" style={{ fontSize: '0.78rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span>평균 매입환율 (원/$)</span>
                            <span className="badge" style={{ fontSize: '0.68rem', padding: '1px 5px', background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-safe)' }}>
                              MTS 매입환율
                            </span>
                          </label>
                          <div style={{ position: 'relative' }}>
                            <span style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', fontWeight: 700, color: 'var(--color-safe)' }}>₩</span>
                            <input
                              type="number"
                              className="input-number"
                              style={{ paddingLeft: '24px', fontWeight: 700 }}
                              value={h.buy_fx_rate !== undefined && h.buy_fx_rate !== null ? h.buy_fx_rate : ''}
                              placeholder={effectiveRate.toFixed(2)}
                              onChange={(e) => handleBuyFxRateChange(String(ast.id), e.target.value)}
                              step={0.1}
                              min={0}
                            />
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: '0.78rem' }}>
                          평균 매입가 (원화) <span className="helper-text">({formatKRW(h.avg_price)})</span>
                        </label>
                        <input
                          type="number"
                          className="input-number"
                          value={h.avg_price !== undefined ? h.avg_price : ''}
                          onChange={(e) => handleAvgPriceKrwChange(String(ast.id), parseFloat(e.target.value) || 0)}
                          step={100}
                          min={0}
                        />
                      </div>
                    )}
                  </div>

                  {/* 미국 자산 전용 실시간 원화 환산 평단가 및 환차익/환차손 미리보기 바 */}
                  {isUs && (
                    <div style={{
                      marginTop: '10px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '8px',
                      background: 'var(--bg-surface)',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-color)',
                      fontSize: '0.78rem'
                    }}>
                      <div>
                        <span style={{ color: 'var(--text-muted)' }}>원화 환산 매수가: </span>
                        <strong style={{ color: 'var(--text-primary)', marginLeft: '4px' }}>{formatKRW(h.avg_price)}</strong>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-muted)' }}>환율 차손익: </span>
                        <strong style={{ color: getProfitColor(effectiveRate - (Number(h.buy_fx_rate) || effectiveRate)), marginLeft: '4px' }}>
                          {(effectiveRate - (Number(h.buy_fx_rate) || effectiveRate)) > 0 ? '+' : ''}
                          {(effectiveRate - (Number(h.buy_fx_rate) || effectiveRate)).toFixed(1)}원/$ (
                          {(effectiveRate - (Number(h.buy_fx_rate) || effectiveRate)) > 0 ? '+' : ''}
                          {(((effectiveRate - (Number(h.buy_fx_rate) || effectiveRate)) / (Number(h.buy_fx_rate) || effectiveRate)) * 100).toFixed(1)}%)
                        </strong>
                        <span style={{ color: 'var(--text-muted)', marginLeft: '4px' }}>(현재 {effectiveRate.toLocaleString()}원)</span>
                      </div>
                    </div>
                  )}

                  {/* 자동 배당 집계 및 배당 시작일 설정 배너 */}
                  <div style={{
                    marginTop: '10px',
                    background: 'rgba(16, 185, 129, 0.08)',
                    border: '1px solid rgba(16, 185, 129, 0.25)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    fontSize: '0.78rem',
                    lineHeight: 1.45
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '6px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--color-safe)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span>💰 배당금 자동 집계 (Total Return)</span>
                        {h.total_dividend_profit > 0 ? (
                          <span style={{ fontWeight: 700 }}>
                            · 누적 {h.dividend_count || 0}회 배당 (총 +{isUs ? formatUSD(h.total_dividend_profit) : formatKRW(h.total_dividend_profit)} 수령 / 주당 +{isUs ? formatUSD(h.cumulative_dividend) : formatKRW(h.cumulative_dividend)})
                          </span>
                        ) : h.cumulative_dividend > 0 ? (
                          <span style={{ fontWeight: 700 }}>
                            · 누적 {h.dividend_count || 0}회 배당 (주당 +{isUs ? formatUSD(h.cumulative_dividend) : formatKRW(h.cumulative_dividend)})
                          </span>
                        ) : null}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.74rem' }}>배당 산정 시작일:</span>
                        <input
                          type="date"
                          className="input-text"
                          style={{ padding: '2px 6px', fontSize: '0.78rem', border: '1px solid var(--border-color)', borderRadius: '4px', width: '130px' }}
                          value={h.first_buy_date || ''}
                          onChange={(e) => handleFirstBuyDateChange(String(ast.id), e.target.value)}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        </fieldset>

        <div style={{ display: 'flex', gap: '10px', marginTop: '24px' }}>
          <button 
            className="btn btn-primary btn-block" 
            onClick={handleSave} 
            disabled={saving || !ledgerReady}
          >
            {saving ? '저장 중...' : tracked ? '💾 원화 예수금만 저장' : '💾 예수금 및 보유 수량/평단가 저장'}
          </button>
        </div>
      </div>
    </div>
  );
}

