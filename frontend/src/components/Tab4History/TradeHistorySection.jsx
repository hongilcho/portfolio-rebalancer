/** TradeHistorySection: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Trash2 } from 'lucide-react';
import { formatKRW, formatUSD, formatQuantity } from '../../utils/formatters';

export default function TradeHistorySection({
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  selectedAccFilter,
  setSelectedAccFilter,
  accounts,
  selectedAssetFilter,
  setSelectedAssetFilter,
  assets,
  loadingTrades,
  trades,
  selectedTradeIds,
  toggleSelectAllTrades,
  toggleSelectTrade,
  handleDeleteSelectedTrades,
  deletingTrades,
}) {
  return (
    <>
      {/* 3. Trade History & Filter Table */}
      <div className="section-card">
        <div className="section-title">
          <span>📜 최근 매매 기록 (Trade History)</span>
        </div>

        {/* Filter Controls */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '16px' }}>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label" style={{ fontSize: '0.8rem' }}>시작일</label>
            <input
              type="date"
              className="input-text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label" style={{ fontSize: '0.8rem' }}>종료일</label>
            <input
              type="date"
              className="input-text"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label" style={{ fontSize: '0.8rem' }}>계좌 필터</label>
            <select
              className="input-select"
              value={selectedAccFilter}
              onChange={(e) => setSelectedAccFilter(e.target.value)}
            >
              <option value="all">전체 계좌</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>
              ))}
            </select>
          </div>

          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label" style={{ fontSize: '0.8rem' }}>종목 필터</label>
            <select
              className="input-select"
              value={selectedAssetFilter}
              onChange={(e) => setSelectedAssetFilter(e.target.value)}
            >
              <option value="all">전체 종목</option>
              {assets.map((a) => (
                <option key={a.id} value={a.id}>{a.market === 'US' ? '🇺🇸 ' : ''}{a.name}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Table */}
        {loadingTrades ? (
          <p style={{ color: 'var(--text-secondary)', padding: '20px 0' }}>매매 기록 조회 중...</p>
        ) : trades.length === 0 ? (
          <div className="alert-banner alert-info">조회된 매매 기록이 없습니다.</div>
        ) : (
          <div>
            <div className="table-container" style={{ maxHeight: '420px' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th style={{ width: '40px', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={selectedTradeIds.length === trades.length && trades.length > 0}
                        onChange={toggleSelectAllTrades}
                      />
                    </th>
                    <th>날짜</th>
                    <th>계좌</th>
                    <th>종목</th>
                    <th>구분</th>
                    <th>수량</th>
                    <th>체결단가</th>
                    <th>체결금액 (원화환산)</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => {
                    const isBuy = t.trade_type === 'BUY';
                    const isSelected = selectedTradeIds.includes(t.id);
                    const isUS = t.currency === 'USD' || t.market === 'US';
                    const fxRate = Number(t.exchange_rate || 1.0);

                    return (
                      <tr key={t.id} style={{ background: isSelected ? 'rgba(99, 102, 241, 0.1)' : undefined }}>
                        <td style={{ textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectTrade(t.id)}
                          />
                        </td>
                        <td>{t.trade_date}</td>
                        <td style={{ fontWeight: 600 }}>[{t.account_type}] {t.account_alias}</td>
                        <td style={{ fontWeight: 600 }}>
                          {isUS ? '🇺🇸 ' : ''}{t.asset_name}
                        </td>
                        <td>
                          <span className={`badge ${isBuy ? 'badge-profit' : 'badge-loss'}`}>
                            {isBuy ? '매수' : '매도'}
                          </span>
                        </td>
                        <td>{formatQuantity(t.quantity)}</td>
                        <td>
                          {isUS ? (
                            <div>
                              <div style={{ fontWeight: 700 }}>{formatUSD(t.price)}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                @ {formatKRW(fxRate)}/$
                              </div>
                            </div>
                          ) : (
                            <div>{formatKRW(t.price)}</div>
                          )}
                        </td>
                        <td>
                          {isUS ? (
                            <div>
                              <div style={{ fontWeight: 700 }}>{formatKRW(t.total_amount_krw || (t.total_amount * fxRate))}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                ({formatUSD(t.total_amount)})
                              </div>
                            </div>
                          ) : (
                            <div style={{ fontWeight: 700 }}>{formatKRW(t.total_amount)}</div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Delete Selection Panel */}
            {selectedTradeIds.length > 0 && (
              <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(251, 113, 133, 0.1)', padding: '14px 18px', borderRadius: 'var(--radius-md)', border: '1px solid rgba(251, 113, 133, 0.3)' }}>
                <span style={{ fontWeight: 600, color: 'var(--color-risk)' }}>
                  🗑️ 선택된 {selectedTradeIds.length}개의 기록 삭제 및 예수금·보유 잔고 복원
                </span>
                <button
                  className="btn btn-danger"
                  onClick={handleDeleteSelectedTrades}
                  disabled={deletingTrades}
                >
                  <Trash2 size={16} />
                  {deletingTrades ? '복원 및 삭제 중...' : '❌ 체크한 기록 모두 삭제'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
