/**
 * 탭 5. 계좌 및 자산 마스터 관리 컴포넌트 (SettingsTab.jsx)
 * =========================================================
 * 포트폴리오에 속한 증권 계좌 및 투자 자산(주식/ETF/금/예금)의 등록/수정/삭제와
 * 시스템 통신 진단 벤치마크 모달(SystemDiagnosticsModal) 연동을 지원합니다.
 */

import React, { useState } from 'react';

import { api } from '../../utils/api';

import SystemDiagnosticsModal from './SystemDiagnosticsModal';
import MarketPricesTable from './MarketPricesTable';
import AccountsTable from './AccountsTable';
import AssetsTable from './AssetsTable';
import AccountEditor from './AccountEditor';
import AssetEditor from './AssetEditor';

export default function SettingsTab({ 
  pricesData, 
  accounts, 
  assets, 
  onSaved,
  currentPortfolioId = 'default'
}) {
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState(false);
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
    is_active: true,
    notes: '',
    is_deposit: false,
    deposit_principal: 10000000,
    interest_rate: 4.0,
    start_date: new Date().toISOString().slice(0, 10),
    maturity_date: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
    early_termination_rate: 0.5,
    tax_rate: 15.4,
    lock_rebalance_sell: true,
    account_id: '',
    account_no: '',
    include_in_rebalance: true,
    is_dividend_cost_deduct: false
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
        annual_limit: accForm.is_unlimited ? 0 : Number(accForm.annual_limit),
        tax_limit: accForm.is_unlimited ? 0 : Number(accForm.tax_limit),
        priority: Number(accForm.priority),
        limit_preference: accForm.limit_preference,
        notes: accForm.notes || '',
        portfolio_id: currentPortfolioId || 'default'
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
      const isDep = Boolean(assetForm.is_deposit);
      const finalTicker = isDep 
        ? (assetForm.ticker.trim() || `DEP-${Date.now().toString(36).slice(-6).toUpperCase()}`)
        : (assetForm.is_gold ? 'M04020000' : assetForm.ticker.trim().toUpperCase());

      const finalAllowedAccs = isDep ? [] : assetForm.allowed_accounts;
      const incRebal = assetForm.include_in_rebalance !== false;

      await api.createAsset({
        name: assetForm.name.trim(),
        ticker: finalTicker,
        market: isDep ? 'KR' : assetForm.market,
        target_weight: incRebal ? Number(assetForm.target_weight) : 0,
        allowed_accounts: finalAllowedAccs,
        is_risk_asset: isDep ? false : Boolean(assetForm.is_risk_asset),
        is_active: Boolean(assetForm.is_active !== false),
        notes: assetForm.notes || '',
        portfolio_id: currentPortfolioId || 'default',
        is_deposit: isDep,
        deposit_principal: Number(assetForm.deposit_principal || 0),
        interest_rate: Number(assetForm.interest_rate || 0),
        start_date: assetForm.start_date || '',
        maturity_date: assetForm.maturity_date || '',
        early_termination_rate: Number(assetForm.early_termination_rate || 0),
        tax_rate: Number(assetForm.tax_rate !== undefined ? assetForm.tax_rate : 15.4),
        lock_rebalance_sell: Boolean(assetForm.lock_rebalance_sell !== false),
        account_no: assetForm.account_no ? assetForm.account_no.trim() : '',
        include_in_rebalance: incRebal,
        is_dividend_cost_deduct: Boolean(assetForm.is_dividend_cost_deduct)
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
      const isDep = Boolean(assetForm.is_deposit);
      const finalTicker = isDep 
        ? (assetForm.ticker.trim() || editAssetTarget.ticker || `DEP-${editAssetTarget.id.slice(0, 6).toUpperCase()}`)
        : (assetForm.is_gold ? 'M04020000' : assetForm.ticker.trim().toUpperCase());

      const finalAllowedAccs = isDep ? [] : assetForm.allowed_accounts;
      const incRebal = assetForm.include_in_rebalance !== false;

      await api.updateAsset(editAssetTarget.id, {
        name: assetForm.name.trim(),
        ticker: finalTicker,
        market: isDep ? 'KR' : assetForm.market,
        target_weight: incRebal ? Number(assetForm.target_weight) : 0,
        allowed_accounts: finalAllowedAccs,
        is_risk_asset: isDep ? false : Boolean(assetForm.is_risk_asset),
        is_active: Boolean(assetForm.is_active !== false),
        notes: assetForm.notes || '',
        is_deposit: isDep,
        deposit_principal: Number(assetForm.deposit_principal || 0),
        interest_rate: Number(assetForm.interest_rate || 0),
        start_date: assetForm.start_date || '',
        maturity_date: assetForm.maturity_date || '',
        early_termination_rate: Number(assetForm.early_termination_rate || 0),
        tax_rate: Number(assetForm.tax_rate !== undefined ? assetForm.tax_rate : 15.4),
        lock_rebalance_sell: Boolean(assetForm.lock_rebalance_sell !== false),
        account_no: assetForm.account_no ? assetForm.account_no.trim() : '',
        include_in_rebalance: incRebal,
        is_dividend_cost_deduct: Boolean(assetForm.is_dividend_cost_deduct)
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
        notes: target.notes || '',
        is_deposit: Boolean(target.is_deposit),
        deposit_principal: Number(target.deposit_principal || 0),
        interest_rate: Number(target.interest_rate || 0),
        start_date: target.start_date || '',
        maturity_date: target.maturity_date || '',
        early_termination_rate: Number(target.early_termination_rate || 0),
        tax_rate: Number(target.tax_rate !== undefined ? target.tax_rate : 15.4),
        lock_rebalance_sell: Boolean(target.lock_rebalance_sell !== false),
        account_id: (target.allowed_accounts && target.allowed_accounts.length > 0) ? String(target.allowed_accounts[0]) : null,
        include_in_rebalance: Boolean(target.include_in_rebalance !== false)
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
  (accounts || []).forEach((a) => {
    accountMapById[String(a.id)] = `[${a.account_type}] ${a.account_alias}`;
  });

  return (
    <div>
      <MarketPricesTable
        setIsDiagnosticsOpen={setIsDiagnosticsOpen}
        assets={assets}
        pricesData={pricesData}
        accountMapById={accountMapById}
      />

      <AccountsTable
        setAccForm={setAccForm}
        setIsAddAccOpen={setIsAddAccOpen}
        accounts={accounts}
        setEditAccTarget={setEditAccTarget}
        handleToggleExhaust={async(id,value)=>{try{await api.toggleLimitExhausted(id,value);await onSaved();}catch(e){alert(e.message);}}}
        handleDeleteAccount={handleDeleteAccount}
      />

      <AssetsTable
        setAssetForm={setAssetForm}
        accounts={accounts}
        setIsAddAssetOpen={setIsAddAssetOpen}
        assets={assets}
        setEditAssetTarget={setEditAssetTarget}
        handleToggleAssetActive={handleToggleAssetActive}
        handleDeleteAsset={handleDeleteAsset}
      />

      <AccountEditor
        isAddAccOpen={isAddAccOpen}
        editAccTarget={editAccTarget}
        setIsAddAccOpen={setIsAddAccOpen}
        setEditAccTarget={setEditAccTarget}
        handleSaveNewAccount={handleSaveNewAccount}
        handleUpdateAccount={handleUpdateAccount}
        accForm={accForm}
        setAccForm={setAccForm}
        saving={saving}
      />

      <AssetEditor
        isAddAssetOpen={isAddAssetOpen}
        editAssetTarget={editAssetTarget}
        setIsAddAssetOpen={setIsAddAssetOpen}
        setEditAssetTarget={setEditAssetTarget}
        setAssetForm={setAssetForm}
        assetForm={assetForm}
        accounts={accounts}
        handleSaveNewAsset={handleSaveNewAsset}
        handleUpdateAsset={handleUpdateAsset}
        saving={saving}
      />

      {/* System Diagnostics Modal */}
      <SystemDiagnosticsModal
        isOpen={isDiagnosticsOpen}
        onClose={() => setIsDiagnosticsOpen(false)}
      />
    </div>
  );
}
