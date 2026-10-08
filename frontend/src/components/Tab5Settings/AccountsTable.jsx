/** AccountsTable: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Plus, Edit3, Trash2 } from 'lucide-react';
import { formatKRW, formatUSD } from '../../utils/formatters';

export default function AccountsTable({
  setAccForm,
  setIsAddAccOpen,
  accounts,
  setEditAccTarget,
  handleDeleteAccount,
  handleToggleExhaust,
}) {
  return (
    <>
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
              {accounts && accounts.length > 0 ? (
                accounts.map((a) => (
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
                    <td>
                      <label><input type="checkbox" aria-label={`${a.account_alias} 한도 소진 완료`} checked={Boolean(a.is_limit_exhausted)} onChange={e=>handleToggleExhaust(a.id,e.target.checked)}/>한도 소진</label><br/>
                      {a.annual_limit > 0 ? formatKRW(a.annual_limit) : '무제한'}
                      {a.is_limit_exhausted && (
                        <span className="badge" style={{ background: '#10B981', color: '#fff', marginLeft: '6px', fontSize: '0.7rem' }}>
                          소진완료
                        </span>
                      )}
                    </td>
                    <td>
                      {a.tax_limit > 0 ? formatKRW(a.tax_limit) : '-'}
                      {a.is_limit_exhausted && a.tax_limit > 0 && (
                        <span className="badge" style={{ background: '#10B981', color: '#fff', marginLeft: '6px', fontSize: '0.7rem' }}>
                          소진완료
                        </span>
                      )}
                    </td>
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
                              priority: a.priority,
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
                ))
              ) : (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-secondary)' }}>
                    등록된 계좌가 없습니다. 상단의 &apos;+ 계좌 추가&apos; 버튼을 눌러 새 계좌를 등록해 주세요.
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
