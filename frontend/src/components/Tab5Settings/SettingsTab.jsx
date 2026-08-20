import React, { useState } from 'react';
import { Plus, Edit3, Trash2, Shield, DollarSign, Database, Tag } from 'lucide-react';
import { api } from '../../utils/api';
import { formatKRW, formatUSD, numToKrMixed } from '../../utils/formatters';
import KoreanNumberInput from '../common/KoreanNumberInput';

export default function SettingsTab({ 
  pricesData, 
  accounts, 
  assets, 
  onSaved 
}) {
  // Account Form State
  const [isAddAccOpen, setIsAddAccOpen] = useState(false);
  const [editAccTarget, setEditAccTarget] = useState(null);
  const [accForm, setAccForm] = useState({
    account_no: '',
    account_alias: '',
    account_type: '종합매매',
    deposit_krw: 0,
    deposit_usd: 0,
    annual_limit: 20000000,
    tax_limit: 0,
    is_unlimited: false,
    priority: 4,
    limit_preference: 'ANNUAL',
    notes: ''
  });

  // Asset Form State
  const [isAddAssetOpen, setIsAddAssetOpen] = useState(false);
  const [editAssetTarget, setEditAssetTarget] = useState(null);
  const [assetForm, setAssetForm] = useState({
    name: '',
    ticker: '',
    market: 'KR',
    target_weight: 10.0,
    allowed_accounts: [],
    is_risk_asset: true,
    is_gold: false,
    notes: ''
  });

  const [saving, setSaving] = useState(false);

  // ACCOUNT HANDLERS
  const handleSaveNewAccount = async (e) => {
    e.preventDefault();
    if (!accForm.account_no.trim() || !accForm.account_alias.trim()) {
      alert('계좌번호와 별명을 입력해 주세요.');
      return;
    }

    setSaving(true);
    try {
      await api.createAccount({
        account_no: accForm.account_no.trim(),
        account_alias: accForm.account_alias.trim(),
        account_type: accForm.account_type,
        deposit_krw: Number(accForm.deposit_krw),
        deposit_usd: Number(accForm.deposit_usd),
        annual_limit: accForm.is_unlimited ? 0 : Number(accForm.annual_limit),
        tax_limit: accForm.is_unlimited ? 0 : Number(accForm.tax_limit),
        priority: Number(accForm.priority),
        limit_preference: accForm.limit_preference,
        notes: accForm.notes || ''
      });
      alert('계좌가 성공적으로 추가되었습니다.');
      setIsAddAccOpen(false);
      onSaved();
    } catch (err) {
      alert(`계좌 등록 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateAccount = async (e) => {
    e.preventDefault();
    if (!editAccTarget) return;

    setSaving(true);
    try {
      await api.updateAccount(editAccTarget.id, {
        account_no: accForm.account_no.trim(),
        account_alias: accForm.account_alias.trim(),
        account_type: accForm.account_type,
        deposit_krw: Number(accForm.deposit_krw),
        deposit_usd: Number(accForm.deposit_usd),
        annual_limit: accForm.is_unlimited ? 0 : Number(accForm.annual_limit),
        tax_limit: accForm.is_unlimited ? 0 : Number(accForm.tax_limit),
        priority: Number(accForm.priority),
        limit_preference: accForm.limit_preference,
        notes: accForm.notes || ''
      });
      alert('계좌가 성공적으로 수정되었습니다.');
      setEditAccTarget(null);
      onSaved();
    } catch (err) {
      alert(`계좌 수정 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAccount = async (id, alias) => {
    if (!window.confirm(`정말 계좌 '${alias}' 및 연결된 보유 잔고를 삭제하시겠습니까?`)) return;
    try {
      await api.deleteAccount(id);
      alert('계좌가 삭제되었습니다.');
      onSaved();
    } catch (err) {
      alert(`삭제 실패: ${err.message}`);
    }
  };

  // ASSET HANDLERS
  const handleSaveNewAsset = async (e) => {
    e.preventDefault();
    if (!assetForm.name.trim()) {
      alert('자산명을 입력해 주세요.');
      return;
    }

    setSaving(true);
    try {
      const finalTicker = assetForm.is_gold ? 'M04020000' : assetForm.ticker.trim().toUpperCase();
      await api.createAsset({
        name: assetForm.name.trim(),
        ticker: finalTicker,
        market: assetForm.market,
        target_weight: Number(assetForm.target_weight),
        allowed_accounts: assetForm.allowed_accounts,
        is_risk_asset: Boolean(assetForm.is_risk_asset),
        is_active: Boolean(assetForm.is_active !== false),
        notes: assetForm.notes || ''
      });
      alert('자산이 성공적으로 등록되었습니다.');
      setIsAddAssetOpen(false);
      onSaved();
    } catch (err) {
      alert(`자산 등록 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateAsset = async (e) => {
    e.preventDefault();
    if (!editAssetTarget) return;

    setSaving(true);
    try {
      const finalTicker = assetForm.is_gold ? 'M04020000' : assetForm.ticker.trim().toUpperCase();
      await api.updateAsset(editAssetTarget.id, {
        name: assetForm.name.trim(),
        ticker: finalTicker,
        market: assetForm.market,
        target_weight: Number(assetForm.target_weight),
        allowed_accounts: assetForm.allowed_accounts,
        is_risk_asset: Boolean(assetForm.is_risk_asset),
        is_active: Boolean(assetForm.is_active !== false),
        notes: assetForm.notes || ''
      });
      alert('자산이 성공적으로 수정되었습니다.');
      setEditAssetTarget(null);
      onSaved();
    } catch (err) {
      alert(`자산 수정 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleToggleAssetActive = async (id, name, currentIsActive) => {
    const target = assets.find((a) => String(a.id) === String(id));
    if (!target) return;

    const actionText = currentIsActive ? '비활성화(보관)' : '활성화';
    const confirmMsg = currentIsActive
      ? `'${name}' 종목을 비활성화(보관)하시겠습니까?\n\n- 과거 매매 기록은 영구 보존됩니다.\n- 1번(대시보드), 2번(목표비중), 3번(리밸런싱) 화면에서 자동으로 숨겨집니다.`
      : `'${name}' 종목을 다시 활성화하시겠습니까?\n\n- 1~3번 탭(대시보드, 목표비중, 리밸런싱)에 다시 정상 표시됩니다.`;
    if (!window.confirm(confirmMsg)) return;

    try {
      await api.updateAsset(id, {
        name: target.name,
        ticker: target.ticker,
        market: target.market,
        target_weight: Number(target.target_weight),
        allowed_accounts: target.allowed_accounts || [],
        is_risk_asset: Boolean(target.is_risk_asset),
        is_active: !currentIsActive,
        notes: target.notes || ''
      });
      alert(`종목이 성공적으로 ${actionText}되었습니다.`);
      onSaved();
    } catch (err) {
      alert(`${actionText} 실패: ${err.message}`);
    }
  };

  const handleDeleteAsset = async (id, name) => {
    if (!window.confirm(`⚠️ 주의: 자산 '${name}' 및 과거 모든 매매 기록이 DB에서 완전히 삭제됩니다!\n\n단순히 1~3번 탭에서 숨기려면 [📦 보관] 기능을 이용하세요.\n\n정말 영구 삭제하시겠습니까?`)) return;
    try {
      await api.deleteAsset(id);
      alert('자산 및 관련 데이터가 삭제되었습니다.');
      onSaved();
    } catch (err) {
      alert(`삭제 실패: ${err.message}`);
    }
  };

  const accountMapById = {};
  accounts.forEach((a) => {
    accountMapById[String(a.id)] = `[${a.account_type}] ${a.account_alias}`;
  });

  return (
    <div>
      {/* 1. Live Market Prices Grid */}
      <div className="section-card">
        <div className="section-title">
          <span>📊 실시간 시세 현황 & 자산별 상태 모니터링</span>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>종목명</th>
                <th>티커</th>
                <th>위험구분</th>
                <th>시장</th>
                <th>목표비중(%)</th>
                <th>현재가(현지)</th>
                <th>원화 환산가</th>
                <th>운용 가능 계좌</th>
                <th>시세 상태</th>
              </tr>
            </thead>
            <tbody>
              {pricesData?.prices?.map((item) => {
                const isUs = item.market === 'US';
                const nativePriceStr = isUs ? formatUSD(item.price_native) : formatKRW(item.price_native);
                const mappedAccs = (item.allowed_accounts || []).map((id) => accountMapById[String(id)] || id);

                return (
                  <tr key={item.id}>
                    <td style={{ fontWeight: 700 }}>{item.name}</td>
                    <td>{item.ticker}</td>
                    <td>
                      <span className={`badge ${item.is_risk_asset !== false ? 'badge-risk' : 'badge-safe'}`}>
                        {item.is_risk_asset !== false ? '🔴 위험' : '🟢 안전'}
                      </span>
                    </td>
                    <td>{isUs ? '🇺🇸 미국' : '🇰🇷 국내'}</td>
                    <td style={{ fontWeight: 600 }}>{item.target_weight.toFixed(1)}%</td>
                    <td>{nativePriceStr}</td>
                    <td style={{ fontWeight: 700 }}>{formatKRW(item.price_krw)}</td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', maxWidth: '280px' }}>
                        {mappedAccs.length > 0 ? (
                          mappedAccs.map((accName, i) => (
                            <span key={i} className="badge" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)', fontSize: '0.72rem' }}>
                              {accName}
                            </span>
                          ))
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>없음</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: '#A5B4FC' }}>
                        {item.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 2. Accounts Management (CRUD) */}
      <div className="section-card">
        <div className="section-title">
          <span>📋 계좌 마스터 관리</span>
          <button 
            className="btn btn-primary btn-sm"
            onClick={() => {
              setAccForm({
                account_no: '',
                account_alias: '',
                account_type: '종합매매',
                deposit_krw: 0,
                deposit_usd: 0,
                annual_limit: 20000000,
                tax_limit: 0,
                is_unlimited: false,
                priority: 4,
                limit_preference: 'ANNUAL',
                notes: ''
              });
              setIsAddAccOpen(true);
            }}
          >
            <Plus size={14} /> 계좌 추가
          </button>
        </div>

        <div className="table-container" style={{ marginBottom: '16px' }}>
          <table className="custom-table">
            <thead>
              <tr>
                <th>계좌번호</th>
                <th>별명</th>
                <th>유형</th>
                <th>원화예수금</th>
                <th>달러예수금</th>
                <th>납입한도</th>
                <th>세액공제한도</th>
                <th>우선순위</th>
                <th>관리</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 600 }}>{a.account_no}</td>
                  <td>{a.account_alias}</td>
                  <td>
                    <span className="badge" style={{ background: 'rgba(255,255,255,0.06)' }}>
                      {a.account_type}
                    </span>
                  </td>
                  <td>{formatKRW(a.deposit_krw)}</td>
                  <td>{formatUSD(a.deposit_usd)}</td>
                  <td>{a.annual_limit > 0 ? formatKRW(a.annual_limit) : '무제한'}</td>
                  <td>{a.tax_limit > 0 ? formatKRW(a.tax_limit) : '-'}</td>
                  <td style={{ fontWeight: 700 }}>{a.priority}</td>
                  <td>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setEditAccTarget(a);
                          setAccForm({
                            account_no: a.account_no,
                            account_alias: a.account_alias,
                            account_type: a.account_type,
                            deposit_krw: a.deposit_krw,
                            deposit_usd: a.deposit_usd,
                            annual_limit: a.annual_limit,
                            tax_limit: a.tax_limit,
                            is_unlimited: a.annual_limit === 0 && a.tax_limit === 0,
                            priority: a.priority || 99,
                            limit_preference: a.limit_preference || 'ANNUAL',
                            notes: a.notes || ''
                          });
                        }}
                      >
                        <Edit3 size={13} /> 수정
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => handleDeleteAccount(a.id, a.account_alias)}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. Assets Management (CRUD) */}
      <div className="section-card">
        <div className="section-title">
          <span>📋 자산(종목) 마스터 관리</span>
          <button 
            className="btn btn-primary btn-sm"
            onClick={() => {
              setAssetForm({
                name: '',
                ticker: '',
                market: 'KR',
                target_weight: 10.0,
                allowed_accounts: accounts.map((a) => String(a.id)),
                is_risk_asset: true,
                is_gold: false,
                notes: ''
              });
              setIsAddAssetOpen(true);
            }}
          >
            <Plus size={14} /> 종목 추가
          </button>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>자산명</th>
                <th>티커/종목코드</th>
                <th>상태</th>
                <th>시장</th>
                <th>목표비중(%)</th>
                <th>위험자산여부</th>
                <th>관리</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((ast) => {
                const isActive = ast.is_active !== false;

                return (
                  <tr key={ast.id} style={{ opacity: isActive ? 1 : 0.65 }}>
                    <td style={{ fontWeight: 700 }}>{ast.name}</td>
                    <td>{ast.ticker}</td>
                    <td>
                      <span className={`badge ${isActive ? 'badge-safe' : ''}`} style={!isActive ? { background: 'rgba(128,128,128,0.2)', color: 'var(--text-muted)' } : {}}>
                        {isActive ? '🟢 활성' : '⚪ 보관(비활성)'}
                      </span>
                    </td>
                    <td>{ast.market === 'KR' ? '🇰🇷 국내' : '🇺🇸 미국'}</td>
                    <td>{isActive ? `${ast.target_weight.toFixed(1)}%` : '-'}</td>
                    <td>
                      <span className={`badge ${ast.is_risk_asset ? 'badge-risk' : 'badge-safe'}`}>
                        {ast.is_risk_asset ? '🔴 위험' : '🟢 안전'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setEditAssetTarget(ast);
                            setAssetForm({
                              name: ast.name,
                              ticker: ast.ticker,
                              market: ast.market,
                              target_weight: ast.target_weight,
                              allowed_accounts: ast.allowed_accounts || [],
                              is_risk_asset: ast.is_risk_asset,
                              is_gold: ast.ticker === 'M04020000' || ast.name.includes('금'),
                              is_active: isActive,
                              notes: ast.notes || ''
                            });
                          }}
                        >
                          <Edit3 size={13} /> 수정
                        </button>
                        <button
                          className={`btn btn-sm ${isActive ? 'btn-secondary' : 'btn-primary'}`}
                          onClick={() => handleToggleAssetActive(ast.id, ast.name, isActive)}
                          title={isActive ? "1~3번 탭에서 숨기기 (과거 매매기록은 보존)" : "1~3번 탭에 다시 표시"}
                        >
                          {isActive ? '📦 보관' : '♻️ 활성화'}
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleDeleteAsset(ast.id, ast.name)}
                          title="종목 및 과거 모든 매매기록 영구 삭제"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

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

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <KoreanNumberInput
                  label="원화 예수금"
                  value={accForm.deposit_krw}
                  onChange={(val) => setAccForm({ ...accForm, deposit_krw: val })}
                  step={10000}
                />
                <div className="form-group">
                  <label className="form-label">달러 예수금 ($)</label>
                  <input
                    type="number"
                    step="10"
                    min="0"
                    className="input-number"
                    value={accForm.deposit_usd}
                    onChange={(e) => setAccForm({ ...accForm, deposit_usd: parseFloat(e.target.value) || 0 })}
                  />
                </div>
              </div>

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

      {/* Asset Add/Edit Modal */}
      {(isAddAssetOpen || editAssetTarget) && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3 className="modal-title">{isAddAssetOpen ? '➕ 신규 종목 등록' : '✏️ 종목 정보 수정'}</h3>
              <button className="btn btn-secondary btn-sm" onClick={() => { setIsAddAssetOpen(false); setEditAssetTarget(null); }}>✕</button>
            </div>

            <form onSubmit={isAddAssetOpen ? handleSaveNewAsset : handleUpdateAsset}>
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

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
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

              <div className="form-group">
                <label className="form-label">운용 가능 계좌 선택</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {accounts.map((a) => {
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
                  })}
                </div>
              </div>

              <button type="submit" className="btn btn-primary btn-block" disabled={saving}>
                {saving ? '저장 중...' : isAddAssetOpen ? '종목 등록하기' : '수정사항 저장하기'}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
