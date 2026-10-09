/** AssetEditor: presentation only; state and API actions stay in the parent. */
import React from 'react';
import KoreanNumberInput from '../common/KoreanNumberInput';

export default function AssetEditor({
  isAddAssetOpen,
  editAssetTarget,
  setIsAddAssetOpen,
  setEditAssetTarget,
  setAssetForm,
  assetForm,
  accounts,
  handleSaveNewAsset,
  handleUpdateAsset,
  saving,
}) {
  return (
    <>
      {/* Asset Add/Edit Modal */}
      {(isAddAssetOpen || editAssetTarget) && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '580px' }}>
            <div className="modal-header">
              <h3 className="modal-title">{isAddAssetOpen ? '➕ 신규 종목 등록' : '✏️ 종목 정보 수정'}</h3>
              <button className="btn btn-secondary btn-sm" onClick={() => { setIsAddAssetOpen(false); setEditAssetTarget(null); }}>✕</button>
            </div>

            {/* Segmented Button: Stock vs Deposit */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '18px', background: 'var(--bg-card-subtle)', padding: '4px', borderRadius: 'var(--radius-md)' }}>
              <button
                type="button"
                disabled={Boolean(editAssetTarget?.is_deposit)}
                onClick={() => setAssetForm({ ...assetForm, is_deposit: false, is_risk_asset: true })}
                style={{
                  flex: 1,
                  padding: '9px 12px',
                  borderRadius: 'var(--radius-sm)',
                  border: 'none',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  cursor: 'pointer',
                  background: !assetForm.is_deposit ? 'var(--accent-primary)' : 'transparent',
                  color: !assetForm.is_deposit ? '#FFFFFF' : 'var(--text-secondary)'
                }}
              >
                📈 주식 / ETF / 금현물
              </button>
              <button
                type="button"
                onClick={() => setAssetForm({
                  ...assetForm,
                  is_deposit: true,
                  is_risk_asset: false,
                  market: 'KR',
                  account_id: assetForm.account_id || (accounts?.[0]?.id ? String(accounts[0].id) : '')
                })}
                style={{
                  flex: 1,
                  padding: '9px 12px',
                  borderRadius: 'var(--radius-sm)',
                  border: 'none',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  cursor: 'pointer',
                  background: assetForm.is_deposit ? 'var(--accent-primary)' : 'transparent',
                  color: assetForm.is_deposit ? '#FFFFFF' : 'var(--text-secondary)'
                }}
                disabled={true}
                title="예금 등록·원금·조건 변경은 5번 탭의 직접 입력 → 예금 장부에서 처리합니다."
              >
                🏦 정기예금
              </button>
            </div>

            <form onSubmit={isAddAssetOpen ? handleSaveNewAsset : handleUpdateAsset}>
              {assetForm.is_deposit ? (
                /* ================= DEPOSIT FORM ================= */
                <div>
                  <p role="note">예금 원금·계약 조건의 등록과 정정은 5번 탭 ‘직접 입력 → 예금 장부’에서 처리합니다.</p>
                  <div style={{
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'rgba(52, 211, 153, 0.1)',
                    border: '1px solid rgba(52, 211, 153, 0.25)',
                    marginBottom: '16px',
                    fontSize: '0.82rem',
                    color: 'var(--text-primary)',
                    lineHeight: '1.4'
                  }}>
                    💡 <strong>정기예금 안내</strong>: 원금에 매일 경과된 <strong>세후 이자(원천징수 15.4% 기본)</strong>가 일할 계산되어 실시간 현재가로 반영됩니다. IRP 규정상 <strong>안전자산(🟢)</strong>으로 자동 분류됩니다.
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '12px' }}>
                    <div className="form-group">
                      <label className="form-label">예금 상품명</label>
                      <input
                        type="text"
                        className="input-text"
                        value={assetForm.name}
                        onChange={(e) => setAssetForm({ ...assetForm, name: e.target.value })}
                        placeholder="예: 신한 정기예금 1년, 국민 특판예금"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">계좌번호 (선택)</label>
                      <input
                        type="text"
                        className="input-text"
                        value={assetForm.account_no || ''}
                        onChange={(e) => setAssetForm({ ...assetForm, account_no: e.target.value })}
                        placeholder="예: 110-123-456789 (은행 계좌번호)"
                      />
                    </div>
                  </div>

                  <KoreanNumberInput
                    label="예금 원금"
                    value={assetForm.deposit_principal}
                    disabled
                    onChange={(val) => setAssetForm({ ...assetForm, deposit_principal: val })}
                    step={1000000}
                  />

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div className="form-group">
                      <label className="form-label">약정 연이율 (%)</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        className="input-number"
                        disabled
                        value={assetForm.interest_rate}
                        onChange={(e) => setAssetForm({ ...assetForm, interest_rate: parseFloat(e.target.value) || 0 })}
                        placeholder="예: 4.0"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">중도해지 연이율 (%) (선택)</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        className="input-number"
                        disabled
                        value={assetForm.early_termination_rate}
                        onChange={(e) => setAssetForm({ ...assetForm, early_termination_rate: parseFloat(e.target.value) || 0 })}
                        placeholder="예: 0.5"
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div className="form-group">
                      <label className="form-label">가입일자</label>
                      <input
                        type="date"
                        className="input-text"
                        disabled
                        value={assetForm.start_date}
                        onChange={(e) => setAssetForm({ ...assetForm, start_date: e.target.value })}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">만기일자</label>
                      <input
                        type="date"
                        className="input-text"
                        disabled
                        value={assetForm.maturity_date}
                        onChange={(e) => setAssetForm({ ...assetForm, maturity_date: e.target.value })}
                        required
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">이자소득세율 (%)</label>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="50"
                        className="input-number"
                        style={{ width: '130px' }}
                        disabled
                        value={assetForm.tax_rate}
                        onChange={(e) => setAssetForm({ ...assetForm, tax_rate: parseFloat(e.target.value) || 0 })}
                        required
                      />
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled
                          onClick={() => setAssetForm({ ...assetForm, tax_rate: 15.4 })}
                        >
                          일반과세 15.4%
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled
                          onClick={() => setAssetForm({ ...assetForm, tax_rate: 9.9 })}
                        >
                          세제우대 9.9%
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setAssetForm({ ...assetForm, tax_rate: 0.0 })}
                        >
                          비과세 0%
                        </button>
                      </div>
                    </div>
                  </div>

                  <div style={{
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    background: assetForm.include_in_rebalance !== false ? 'rgba(59, 130, 246, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                    border: `1px solid ${assetForm.include_in_rebalance !== false ? 'rgba(59, 130, 246, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
                    marginBottom: '16px'
                  }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600, fontSize: '0.9rem' }}>
                      <input
                        type="checkbox"
                        checked={assetForm.include_in_rebalance !== false}
                        onChange={(e) => {
                          const checked = e.target.checked;
                          setAssetForm({
                            ...assetForm,
                            include_in_rebalance: checked,
                            target_weight: checked ? (assetForm.target_weight || 10.0) : 0.0
                          });
                        }}
                      />
                      ⚖️ <strong>포트폴리오 비중 및 리밸런싱에 포함</strong>
                    </label>
                    <p style={{ margin: '6px 0 0 24px', fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                      {assetForm.include_in_rebalance !== false
                        ? '✅ 거치식 포트폴리오 등: 예금 금액이 포트폴리오 비중(%)에 포함되며 목표 비중을 설정합니다.'
                        : '🚫 적립식 포트폴리오 등: 예금이 포트폴리오 비중 및 괴리율 계산에서 제외되며, 순수 주식/ETF만으로 100% 비중을 맞춥니다. (자산 종합 요약/총 자산 평가액에는 정상 포함)'}
                    </p>
                  </div>

                  {assetForm.include_in_rebalance !== false ? (
                    <div className="form-group">
                      <label className="form-label">목표 비중 (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        className="input-number"
                        value={assetForm.target_weight}
                        onChange={(e) => setAssetForm({ ...assetForm, target_weight: parseFloat(e.target.value) || 0 })}
                        required
                      />
                    </div>
                  ) : (
                    <div className="form-group" style={{ opacity: 0.7 }}>
                      <label className="form-label">목표 비중 (%) - 비중 제외 적용 중</label>
                      <input
                        type="text"
                        className="input-text"
                        value="0.0% (포트폴리오 비중 제외)"
                        disabled
                      />
                    </div>
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '10px', marginBottom: '16px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem' }}>
                      <input
                        type="checkbox"
                        checked={assetForm.lock_rebalance_sell !== false}
                        onChange={(e) => setAssetForm({ ...assetForm, lock_rebalance_sell: e.target.checked })}
                      />
                      🛡️ <strong>리밸런싱 매도 방지</strong> (중도해지 손실 방지를 위해 자동 매도 대상에서 보호)
                    </label>

                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem' }}>
                      <input
                        type="checkbox"
                        checked={assetForm.is_active !== false}
                        onChange={(e) => setAssetForm({ ...assetForm, is_active: e.target.checked })}
                      />
                      활성 종목 (대시보드 및 리밸런싱에 표시)
                    </label>
                  </div>
                </div>
              ) : (
                /* ================= STOCK / ETF / GOLD FORM ================= */
                <div>
                  <div style={{ marginBottom: '12px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem' }}>
                      <input
                        type="checkbox"
                        checked={assetForm.is_gold}
                        onChange={(e) => {
                          const isG = e.target.checked;
                          setAssetForm({
                            ...assetForm,
                            is_gold: isG,
                            name: isG ? 'KRX 금현물' : assetForm.name,
                            ticker: isG ? 'M04020000' : assetForm.ticker
                          });
                        }}
                      />
                      KRX 실물 금 등록 (티커 M04020000 자동 매핑)
                    </label>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div className="form-group">
                      <label className="form-label">자산명</label>
                      <input
                        type="text"
                        className="input-text"
                        value={assetForm.name}
                        onChange={(e) => setAssetForm({ ...assetForm, name: e.target.value })}
                        placeholder="예: KODEX 200, SCHD"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">종목코드 / 티커</label>
                      <input
                        type="text"
                        className="input-text"
                        value={assetForm.ticker}
                        onChange={(e) => setAssetForm({ ...assetForm, ticker: e.target.value })}
                        placeholder="예: 069500, SPY"
                        disabled={assetForm.is_gold}
                        required
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div className="form-group">
                      <label className="form-label">시장 구분</label>
                      <select
                        className="input-select"
                        value={assetForm.market}
                        onChange={(e) => setAssetForm({ ...assetForm, market: e.target.value })}
                      >
                        <option value="KR">🇰🇷 국내 (KRX)</option>
                        <option value="US">🇺🇸 미국 (US)</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">목표 비중 (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="100"
                        className="input-number"
                        value={assetForm.target_weight}
                        onChange={(e) => setAssetForm({ ...assetForm, target_weight: parseFloat(e.target.value) || 0 })}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem' }}>
                      <input
                        type="checkbox"
                        checked={assetForm.is_risk_asset}
                        onChange={(e) => setAssetForm({ ...assetForm, is_risk_asset: e.target.checked })}
                      />
                      위험자산으로 분류 (IRP 70%)
                    </label>

                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem' }}>
                      <input
                        type="checkbox"
                        checked={assetForm.is_active !== false}
                        onChange={(e) => setAssetForm({ ...assetForm, is_active: e.target.checked })}
                      />
                      활성 종목 (1~3번 탭 표시)
                    </label>
                  </div>

                  <div style={{ marginBottom: '16px', padding: '10px 12px', background: 'rgba(16, 185, 129, 0.08)', borderRadius: 'var(--radius-md)', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--color-safe)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span>💰 자동 배당 및 총수익(Total Return) 추적</span>
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px', lineHeight: 1.45 }}>
                      모든 종목의 배당 데이터가 자동으로 집계되어 손익 및 수익률에 Total Return으로 반영됩니다. 나무 MTS의 매입단가는 원본 그대로 100% 보존됩니다.
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">운용 가능 계좌 선택</label>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {accounts && accounts.length > 0 ? (
                        accounts.map((a) => {
                          const isChecked = assetForm.allowed_accounts.map(String).includes(String(a.id));
                          return (
                            <button
                              key={a.id}
                              type="button"
                              onClick={() => {
                                const current = assetForm.allowed_accounts.map(String);
                                const next = isChecked ? current.filter((x) => x !== String(a.id)) : [...current, String(a.id)];
                                setAssetForm({ ...assetForm, allowed_accounts: next });
                              }}
                              style={{
                                padding: '5px 10px',
                                borderRadius: 'var(--radius-full)',
                                fontSize: '0.8rem',
                                fontWeight: 600,
                                cursor: 'pointer',
                                border: isChecked ? '1px solid var(--accent-primary)' : '1px solid var(--border-color)',
                                background: isChecked ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                                color: isChecked ? '#FFFFFF' : 'var(--text-secondary)'
                              }}
                            >
                              {isChecked && '✓ '} [{a.account_type}] {a.account_alias}
                            </button>
                          );
                        })
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
                          등록된 계좌가 없습니다. 먼저 계좌를 추가해 주세요.
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <button type="submit" className="btn btn-primary btn-block" disabled={saving}>
                {saving ? '저장 중...' : isAddAssetOpen ? '종목 등록하기' : '수정사항 저장하기'}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
