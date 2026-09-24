import React, { useState, useEffect } from 'react';
import { Save } from 'lucide-react';
import { api } from '../../utils/api';

export default function WeightsTab({ assets, accounts, onSaved }) {
  const [weightInputs, setWeightInputs] = useState({});
  const [accountInputs, setAccountInputs] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    const wMap = {};
    const aMap = {};
    assets.forEach((ast) => {
      wMap[String(ast.id)] = ast.include_in_rebalance === false ? 0 : Number(ast.target_weight || 0);
      aMap[String(ast.id)] = (ast.allowed_accounts || []).map(String);
    });
    setWeightInputs(wMap);
    setAccountInputs(aMap);
  }, [assets]);

  const handleWeightChange = (assetId, val) => {
    const num = Math.min(100, Math.max(0, parseFloat(val) || 0));
    setWeightInputs((prev) => ({
      ...prev,
      [assetId]: num
    }));
  };

  const toggleAccount = (assetId, accId) => {
    setAccountInputs((prev) => {
      const currentList = prev[assetId] || [];
      const exists = currentList.includes(String(accId));
      const nextList = exists
        ? currentList.filter((id) => id !== String(accId))
        : [...currentList, String(accId)];
      return {
        ...prev,
        [assetId]: nextList
      };
    });
  };

  const activeAssets = assets.filter((ast) => ast.is_active !== false);
  const rebalanceAssets = activeAssets.filter((ast) => ast.include_in_rebalance !== false);
  const totalWeight = rebalanceAssets.reduce((sum, ast) => sum + (Number(weightInputs[String(ast.id)]) || 0), 0);
  const is100 = Math.abs(totalWeight - 100.0) < 0.05;

  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    try {
      const payload = assets.map((ast) => {
        const isActive = ast.is_active !== false;
        const incRebal = ast.include_in_rebalance !== false;
        return {
          id: String(ast.id),
          name: ast.name,
          ticker: ast.ticker,
          market: ast.market,
          target_weight: (isActive && incRebal) ? Number(weightInputs[String(ast.id)] || 0) : 0,
          allowed_accounts: accountInputs[String(ast.id)] || [],
          is_risk_asset: Boolean(ast.is_risk_asset),
          is_active: isActive,
          notes: ast.notes || '',
          is_deposit: Boolean(ast.is_deposit),
          deposit_principal: Number(ast.deposit_principal || 0),
          interest_rate: Number(ast.interest_rate || 0),
          start_date: ast.start_date || '',
          maturity_date: ast.maturity_date || '',
          early_termination_rate: Number(ast.early_termination_rate || 0),
          tax_rate: Number(ast.tax_rate !== undefined ? ast.tax_rate : 15.4),
          lock_rebalance_sell: Boolean(ast.lock_rebalance_sell !== false),
          account_id: (ast.allowed_accounts && ast.allowed_accounts.length > 0) ? String(ast.allowed_accounts[0]) : null,
          account_no: ast.account_no || '',
          include_in_rebalance: incRebal
        };
      });

      await api.batchUpdateWeights(payload);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      onSaved();
    } catch (err) {
      alert(`저장 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="section-card">
      <div className="section-title">
        <span>🎯 포트폴리오 목표 비중 및 계좌 매핑 설정</span>
        <span style={{ fontSize: '0.9rem', color: is100 ? 'var(--color-safe)' : 'var(--color-warning)' }}>
          합계: <strong>{totalWeight.toFixed(1)}%</strong> {is100 ? '✅ (100% 일치)' : '⚠️ (100%를 맞춰주세요)'}
        </span>
      </div>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '24px' }}>
        현재 활성화된 자산들의 목표 비중을 슬라이더 또는 숫자로 설정하고, 각 자산을 매수할 수 있는 계좌를 선택해 주세요.
      </p>

      {activeAssets.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--text-secondary)', background: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-md)', border: '1px dashed var(--border-color)' }}>
          현재 포트폴리오에 등록된 활성 자산(종목)이 없습니다. &apos;기초 환경 세팅&apos; 탭에서 종목을 먼저 추가해 주세요.
        </div>
      ) : (
        activeAssets.map((asset) => {
        const aid = String(asset.id);
        const incRebal = asset.include_in_rebalance !== false;
        const wVal = weightInputs[aid] !== undefined ? weightInputs[aid] : (incRebal ? asset.target_weight : 0);
        const currentAccs = accountInputs[aid] || [];

        return (
          <div 
            key={asset.id} 
            style={{ 
              background: 'var(--bg-card-subtle)', 
              padding: '20px', 
              borderRadius: 'var(--radius-md)', 
              marginBottom: '16px',
              border: '1px solid var(--border-color)',
              opacity: incRebal ? 1 : 0.85
            }}
          >
            {/* Header: Asset Name & Risk Badge */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: '1.05rem' }}>{asset.name}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.88rem', marginLeft: '8px' }}>
                  ({asset.is_deposit ? (asset.account_no || '예금') : asset.ticker} | {asset.market === 'KR' ? '🇰🇷 국내' : '🇺🇸 미국'})
                </span>
                {!incRebal && (
                  <span className="badge" style={{ marginLeft: '8px', fontSize: '0.78rem', background: 'rgba(156, 163, 175, 0.2)', color: 'var(--text-muted)' }}>
                    ⚖️ 비중/리밸런싱 제외 자산
                  </span>
                )}
              </div>
              <span className={`badge ${asset.is_risk_asset ? 'badge-risk' : 'badge-safe'}`}>
                {asset.is_risk_asset ? '🔴 위험자산 (IRP 70% 제한)' : '🟢 안전자산'}
              </span>
            </div>

            {/* Controls Grid */}
            {incRebal ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '20px', alignItems: 'center', marginBottom: '16px' }}>
                {/* Slider */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="0.1"
                    value={wVal}
                    onChange={(e) => handleWeightChange(aid, e.target.value)}
                    style={{ flex: 1, accentColor: 'var(--accent-primary)', height: '6px', cursor: 'pointer' }}
                  />
                </div>

                {/* Number Input */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    className="input-number"
                    style={{ width: '90px', textAlign: 'right', fontWeight: 700 }}
                    value={wVal}
                    onChange={(e) => handleWeightChange(aid, e.target.value)}
                  />
                  <span style={{ fontWeight: 700, color: 'var(--text-secondary)' }}>%</span>
                </div>
              </div>
            ) : (
              <div style={{
                background: 'rgba(156, 163, 175, 0.08)',
                border: '1px dashed var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                padding: '12px 16px',
                marginBottom: '16px',
                fontSize: '0.88rem',
                color: 'var(--text-secondary)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <span>🚫 <strong>포트폴리오 비중 제외 적용 중</strong> (목표 비중 0.0% 고정, 100% 합계 검증 대상에서 제외됩니다. 환경 세팅에서 변경 가능)</span>
                <span style={{ fontWeight: 700, color: 'var(--text-muted)' }}>0.0%</span>
              </div>
            )}

            {/* Allowed Accounts Multi-select Chips */}
            <div>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                매수/운용 가능 계좌 선택:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {accounts.map((acc) => {
                  const isChecked = currentAccs.includes(String(acc.id));
                  return (
                    <button
                      key={acc.id}
                      type="button"
                      onClick={() => toggleAccount(aid, acc.id)}
                      style={{
                        padding: '6px 12px',
                        borderRadius: 'var(--radius-full)',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        border: isChecked ? '1px solid var(--accent-primary)' : '1px solid var(--border-color)',
                        background: isChecked ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                        color: isChecked ? '#FFFFFF' : 'var(--text-secondary)',
                        transition: 'all 0.15s ease'
                      }}
                    >
                      {isChecked && '✓ '}
                      [{acc.account_type}] {acc.account_alias}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        );
      }))}

      {/* Save Button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px' }}>
        <button 
          className="btn btn-primary"
          style={{ padding: '12px 28px', fontSize: '1rem' }}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? '저장 중...' : saveSuccess ? '✅ 저장 완료!' : (
            <>
              <Save size={18} /> 목표 비중 및 계좌 매핑 저장
            </>
          )}
        </button>
      </div>
    </div>
  );
}
