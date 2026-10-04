/** AssetsTable: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Plus, Edit3, Trash2 } from 'lucide-react';

export default function AssetsTable({
  setAssetForm,
  accounts,
  setIsAddAssetOpen,
  assets,
  setEditAssetTarget,
  handleToggleAssetActive,
  handleDeleteAsset,
}) {
  return (
    <>
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
                account_id: accounts?.[0]?.id ? String(accounts[0].id) : '',
                account_no: '',
                include_in_rebalance: true,
                is_dividend_cost_deduct: false
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
                <th>티커 / 계좌번호</th>
                <th>상태</th>
                <th>시장</th>
                <th>목표비중(%)</th>
                <th>위험자산여부</th>
                <th>관리</th>
              </tr>
            </thead>
            <tbody>
              {assets && assets.length > 0 ? (
                assets.map((ast) => {
                  const isActive = ast.is_active !== false;

                  return (
                    <tr key={ast.id} style={{ opacity: isActive ? 1 : 0.65 }}>
                      <td style={{ fontWeight: 700 }}>
                        {ast.name}
                        {ast.is_deposit && (
                          <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                            🏦 예금 (연 {ast.interest_rate}%)
                          </span>
                        )}
                        {ast.include_in_rebalance === false && (
                          <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(156, 163, 175, 0.2)', color: 'var(--text-muted)' }}>
                            비중 제외
                          </span>
                        )}
                        {ast.is_deposit && ast.account_no && (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 400, marginTop: '2px' }}>
                            계좌: {ast.account_no}
                          </div>
                        )}
                      </td>
                      <td>{ast.is_deposit ? (ast.account_no || '-') : ast.ticker}</td>
                      <td>
                        <span className={`badge ${isActive ? 'badge-safe' : ''}`} style={!isActive ? { background: 'rgba(128,128,128,0.2)', color: 'var(--text-muted)' } : {}}>
                          {isActive ? '🟢 활성' : '⚪ 보관(비활성)'}
                        </span>
                      </td>
                      <td>{ast.market === 'KR' ? '🇰🇷 국내' : '🇺🇸 미국'}</td>
                      <td>{isActive ? (ast.include_in_rebalance === false ? '0.0% (제외)' : `${ast.target_weight.toFixed(1)}%`) : '-'}</td>
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
                                notes: ast.notes || '',
                                is_deposit: Boolean(ast.is_deposit),
                                deposit_principal: ast.deposit_principal || 10000000,
                                interest_rate: ast.interest_rate || 4.0,
                                start_date: ast.start_date || new Date().toISOString().slice(0, 10),
                                maturity_date: ast.maturity_date || new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
                                early_termination_rate: ast.early_termination_rate || 0.0,
                                tax_rate: ast.tax_rate !== undefined ? ast.tax_rate : 15.4,
                                lock_rebalance_sell: ast.lock_rebalance_sell !== undefined ? ast.lock_rebalance_sell : true,
                                account_id: (ast.allowed_accounts && ast.allowed_accounts.length > 0) ? String(ast.allowed_accounts[0]) : '',
                                account_no: ast.account_no || '',
                                include_in_rebalance: ast.include_in_rebalance !== undefined ? Boolean(ast.include_in_rebalance) : true,
                                is_dividend_cost_deduct: Boolean(ast.is_dividend_cost_deduct)
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
                })
              ) : (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-secondary)' }}>
                    등록된 자산(종목)이 없습니다. 상단의 &apos;+ 종목 추가&apos; 버튼을 눌러 새 종목을 등록해 주세요.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
