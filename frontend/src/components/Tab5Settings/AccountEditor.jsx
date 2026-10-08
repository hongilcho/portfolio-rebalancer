/** AccountEditor: presentation only; state and API actions stay in the parent. */
import React from 'react';
import KoreanNumberInput from '../common/KoreanNumberInput';

export default function AccountEditor({
  isAddAccOpen,
  editAccTarget,
  setIsAddAccOpen,
  setEditAccTarget,
  handleSaveNewAccount,
  handleUpdateAccount,
  accForm,
  setAccForm,
  saving,
}) {
  return (
    <>
      {/* Account Add/Edit Modal */}
      {(isAddAccOpen || editAccTarget) && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3 className="modal-title">{isAddAccOpen ? '➕ 신규 계좌 등록' : '✏️ 계좌 정보 수정'}</h3>
              <button className="btn btn-secondary btn-sm" onClick={() => { setIsAddAccOpen(false); setEditAccTarget(null); }}>✕</button>
            </div>

            <form onSubmit={isAddAccOpen ? handleSaveNewAccount : handleUpdateAccount}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">계좌번호</label>
                  <input
                    type="text"
                    className="input-text"
                    value={accForm.account_no}
                    onChange={(e) => setAccForm({ ...accForm, account_no: e.target.value })}
                    placeholder="예: 110-123-456789"
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">계좌 별명</label>
                  <input
                    type="text"
                    className="input-text"
                    value={accForm.account_alias}
                    onChange={(e) => setAccForm({ ...accForm, account_alias: e.target.value })}
                    placeholder="예: 주력 ISA 계좌"
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">계좌 유형</label>
                  <select
                    className="input-select"
                    value={accForm.account_type}
                    onChange={(e) => setAccForm({ ...accForm, account_type: e.target.value })}
                  >
                    <option value="종합매매">종합매매</option>
                    <option value="연금저축">연금저축</option>
                    <option value="IRP">IRP</option>
                    <option value="ISA">ISA</option>
                    <option value="CMA">CMA</option>
                    <option value="금현물">금현물</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">매수 우선순위 (작을수록 우선)</label>
                  <input
                    type="number"
                    min="1"
                    className="input-number"
                    value={accForm.priority}
                    onChange={(e) => setAccForm({ ...accForm, priority: parseInt(e.target.value) || 99 })}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem' }}>
                  <input
                    type="checkbox"
                    checked={accForm.is_unlimited}
                    onChange={(e) => setAccForm({ ...accForm, is_unlimited: e.target.checked })}
                  />
                  한도 제한 없음 (종합매매/CMA 등)
                </label>
              </div>

              {!accForm.is_unlimited && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <KoreanNumberInput
                    label="연간 납입 한도"
                    value={accForm.annual_limit}
                    onChange={(val) => setAccForm({ ...accForm, annual_limit: val })}
                    step={1000000}
                  />
                  <KoreanNumberInput
                    label="세액공제 한도"
                    value={accForm.tax_limit}
                    onChange={(val) => setAccForm({ ...accForm, tax_limit: val })}
                    step={1000000}
                  />
                </div>
              )}

              <p>예수금·초기 잔고는 4번 탭의 장부 확인 및 정정에서 관리합니다.</p>

              <div className="form-group">
                <label className="form-label">메모</label>
                <input
                  type="text"
                  className="input-text"
                  value={accForm.notes}
                  onChange={(e) => setAccForm({ ...accForm, notes: e.target.value })}
                  placeholder="계좌 관련 메모"
                />
              </div>

              <button type="submit" className="btn btn-primary btn-block" disabled={saving}>
                {saving ? '저장 중...' : isAddAccOpen ? '계좌 등록하기' : '수정사항 저장하기'}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
