/** TradeBatchForm: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Plus, Save } from 'lucide-react';
import { formatKRW, formatUSD } from '../../utils/formatters';

export default function TradeBatchForm({
  tradeDate,
  setTradeDate,
  buyRows,
  assets,
  updateBuyRow,
  accounts,
  removeBuyRow,
  usdKrw,
  addBuyRow,
  sellRows,
  holdingsError,
  accountHoldingsMap,
  updateSellRow,
  removeSellRow,
  addSellRow,
  handleSaveBatchTrades,
  savingBatch,
}) {
  return (
    <>
      {/* 2. Batch Trade Input Form */}
      <div className="section-card">
        <div className="section-title">
          <span>📝 실제 매매 기록 (일괄 입력)</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>체결 일자:</span>
            <input
              type="date"
              className="input-text"
              style={{ width: '150px', padding: '6px 10px' }}
              value={tradeDate}
              onChange={(e) => setTradeDate(e.target.value)}
            />
          </div>
        </div>

        <div className="trade-forms-grid">
          {/* 🔴 BUY Column */}
          <div style={{ background: 'var(--bg-card-subtle)', padding: '18px', borderRadius: 'var(--radius-md)', border: '1px solid rgba(248, 113, 113, 0.2)' }}>
            <h4 style={{ color: 'var(--color-profit)', fontWeight: 700, marginBottom: '14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🔴 매수 (Buy) 입력</span>
              <span style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>{buyRows.length}건</span>
            </h4>

            {buyRows.map((row) => {
              const allowedForAcc = assets.filter((ast) =>
                (ast.allowed_accounts || []).map(String).includes(String(row.accountId))
              );
              const selectedAst = assets.find((a) => String(a.id) === String(row.assetId));
              const isUS = selectedAst?.market === 'US';

              return (
                <div key={row.id} className="trade-row-card">
                  {/* Desktop Layout */}
                  <div className="trade-row-desktop">
                    <select
                      className="input-select"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.accountId}
                      onChange={(e) => updateBuyRow(row.id, 'accountId', e.target.value)}
                    >
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>
                      ))}
                    </select>

                    <select
                      className="input-select"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.assetId}
                      onChange={(e) => updateBuyRow(row.id, 'assetId', e.target.value)}
                    >
                      <option value="">종목 선택</option>
                      {allowedForAcc.map((ast) => (
                        <option key={ast.id} value={ast.id}>{ast.market === 'US' ? '🇺🇸 ' : ''}{ast.name}</option>
                      ))}
                    </select>

                    <input
                      type="number"
                      placeholder="수량"
                      className="input-number"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.quantity || ''}
                      onChange={(e) => updateBuyRow(row.id, 'quantity', parseFloat(e.target.value) || 0)}
                      min={0}
                      step={1}
                    />

                    <input
                      type="number"
                      placeholder={isUS ? '단가($ USD)' : '단가(원)'}
                      className="input-number"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.price || ''}
                      onChange={(e) => updateBuyRow(row.id, 'price', parseFloat(e.target.value) || 0)}
                      min={0}
                      step={isUS ? 0.01 : 100}
                    />

                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ padding: '6px 8px' }}
                      onClick={() => removeBuyRow(row.id)}
                      title="행 삭제"
                    >
                      ✕
                    </button>
                  </div>

                  {/* Mobile Layout */}
                  <div className="trade-row-mobile">
                    <div className="trade-row-mobile-line1">
                      <select
                        className="input-select"
                        value={row.accountId}
                        onChange={(e) => updateBuyRow(row.id, 'accountId', e.target.value)}
                      >
                        {accounts.map((a) => (
                          <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>
                        ))}
                      </select>

                      <select
                        className="input-select"
                        value={row.assetId}
                        onChange={(e) => updateBuyRow(row.id, 'assetId', e.target.value)}
                      >
                        <option value="">종목 선택</option>
                        {allowedForAcc.map((ast) => (
                          <option key={ast.id} value={ast.id}>{ast.market === 'US' ? '🇺🇸 ' : ''}{ast.name}</option>
                        ))}
                      </select>
                    </div>

                    <div className="trade-row-mobile-line2">
                      <input
                        type="number"
                        placeholder="수량 (주)"
                        className="input-number"
                        value={row.quantity || ''}
                        onChange={(e) => updateBuyRow(row.id, 'quantity', parseFloat(e.target.value) || 0)}
                        min={0}
                        step={1}
                      />

                      <input
                        type="number"
                        placeholder={isUS ? '단가 ($ USD)' : '체결단가 (원)'}
                        className="input-number"
                        value={row.price || ''}
                        onChange={(e) => updateBuyRow(row.id, 'price', parseFloat(e.target.value) || 0)}
                        min={0}
                        step={isUS ? 0.01 : 100}
                      />

                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '8px 12px' }}
                        onClick={() => removeBuyRow(row.id)}
                        title="행 삭제"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* US Asset Applied FX Rate Card & Preview */}
                  {isUS && (
                    <div style={{
                      marginTop: '6px',
                      padding: '8px 12px',
                      background: 'rgba(59, 130, 246, 0.08)',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid rgba(59, 130, 246, 0.25)',
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '8px',
                      fontSize: '0.8rem'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontWeight: 600, color: 'var(--accent-primary)' }}>🇺🇸 체결환율:</span>
                        <input
                          type="number"
                          step="0.1"
                          style={{ width: '85px', padding: '3px 6px', fontSize: '0.8rem' }}
                          className="input-number"
                          value={row.exchangeRate ?? usdKrw}
                          onChange={(e) => updateBuyRow(row.id, 'exchangeRate', parseFloat(e.target.value) || 0)}
                        />
                        <span>원/$</span>
                      </div>
                      <div style={{ color: 'var(--text-secondary)' }}>
                        1주당 ≈ <b>{formatKRW(row.price * (row.exchangeRate || usdKrw))}</b>
                        {row.quantity > 0 && (
                          <span> | 총액: <b>{formatUSD(row.quantity * row.price)}</b> (≈ {formatKRW(row.quantity * row.price * (row.exchangeRate || usdKrw))})</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            <button className="btn btn-secondary btn-sm btn-block" onClick={addBuyRow}>
              <Plus size={14} /> 매수 추가
            </button>
          </div>

          {/* 🔵 SELL Column */}
          <div style={{ background: 'var(--bg-card-subtle)', padding: '18px', borderRadius: 'var(--radius-md)', border: '1px solid rgba(96, 165, 250, 0.2)' }}>
            <h4 style={{ color: 'var(--color-loss)', fontWeight: 700, marginBottom: '14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🔵 매도 (Sell) 입력</span>
              <span style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>{sellRows.length}건</span>
            </h4>

            {holdingsError && (
              <p role="alert" style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                보유 잔고를 불러오지 못했습니다. 화면을 새로고침하여 다시 조회해주세요.
              </p>
            )}

            {sellRows.map((row) => {
              const accHoldings = (accountHoldingsMap[String(row.accountId)] || []).filter((h) => h.quantity > 0);
              const selectedAst = assets.find((a) => String(a.id) === String(row.assetId));
              const isUS = selectedAst?.market === 'US';

              return (
                <div key={row.id} className="trade-row-card">
                  {/* Desktop Layout */}
                  <div className="trade-row-desktop">
                    <select
                      className="input-select"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.accountId}
                      onChange={(e) => updateSellRow(row.id, 'accountId', e.target.value)}
                    >
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>
                      ))}
                    </select>

                    <select
                      className="input-select"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.assetId}
                      onChange={(e) => updateSellRow(row.id, 'assetId', e.target.value)}
                    >
                      <option value="">보유 종목 선택</option>
                      {accHoldings.map((h) => {
                        const holdingAst = assets.find(a => String(a.id) === String(h.asset_id));
                        return (
                          <option key={h.asset_id} value={h.asset_id}>
                            {holdingAst?.market === 'US' ? '🇺🇸 ' : ''}{h.asset_name} (잔고: {h.quantity})
                          </option>
                        );
                      })}
                    </select>

                    <input
                      type="number"
                      placeholder="수량"
                      className="input-number"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.quantity || ''}
                      onChange={(e) => updateSellRow(row.id, 'quantity', parseFloat(e.target.value) || 0)}
                      min={0}
                      step={1}
                    />

                    <input
                      type="number"
                      placeholder={isUS ? '단가($ USD)' : '단가(원)'}
                      className="input-number"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.price || ''}
                      onChange={(e) => updateSellRow(row.id, 'price', parseFloat(e.target.value) || 0)}
                      min={0}
                      step={isUS ? 0.01 : 100}
                    />

                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ padding: '6px 8px' }}
                      onClick={() => removeSellRow(row.id)}
                      title="행 삭제"
                    >
                      ✕
                    </button>
                  </div>

                  {/* Mobile Layout */}
                  <div className="trade-row-mobile">
                    <div className="trade-row-mobile-line1">
                      <select
                        className="input-select"
                        value={row.accountId}
                        onChange={(e) => updateSellRow(row.id, 'accountId', e.target.value)}
                      >
                        {accounts.map((a) => (
                          <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>
                        ))}
                      </select>

                      <select
                        className="input-select"
                        value={row.assetId}
                        onChange={(e) => updateSellRow(row.id, 'assetId', e.target.value)}
                      >
                        <option value="">보유 종목 선택</option>
                        {accHoldings.map((h) => {
                          const holdingAst = assets.find(a => String(a.id) === String(h.asset_id));
                          return (
                            <option key={h.asset_id} value={h.asset_id}>
                              {holdingAst?.market === 'US' ? '🇺🇸 ' : ''}{h.asset_name} (잔고: {h.quantity})
                            </option>
                          );
                        })}
                      </select>
                    </div>

                    <div className="trade-row-mobile-line2">
                      <input
                        type="number"
                        placeholder="수량 (주)"
                        className="input-number"
                        value={row.quantity || ''}
                        onChange={(e) => updateSellRow(row.id, 'quantity', parseFloat(e.target.value) || 0)}
                        min={0}
                        step={1}
                      />

                      <input
                        type="number"
                        placeholder={isUS ? '단가 ($ USD)' : '체결단가 (원)'}
                        className="input-number"
                        value={row.price || ''}
                        onChange={(e) => updateSellRow(row.id, 'price', parseFloat(e.target.value) || 0)}
                        min={0}
                        step={isUS ? 0.01 : 100}
                      />

                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '8px 12px' }}
                        onClick={() => removeSellRow(row.id)}
                        title="행 삭제"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* US Asset Applied FX Rate Card & Preview */}
                  {isUS && (
                    <div style={{
                      marginTop: '6px',
                      padding: '8px 12px',
                      background: 'rgba(59, 130, 246, 0.08)',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid rgba(59, 130, 246, 0.25)',
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '8px',
                      fontSize: '0.8rem'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontWeight: 600, color: 'var(--accent-primary)' }}>🇺🇸 체결환율:</span>
                        <input
                          type="number"
                          step="0.1"
                          style={{ width: '85px', padding: '3px 6px', fontSize: '0.8rem' }}
                          className="input-number"
                          value={row.exchangeRate ?? usdKrw}
                          onChange={(e) => updateSellRow(row.id, 'exchangeRate', parseFloat(e.target.value) || 0)}
                        />
                        <span>원/$</span>
                      </div>
                      <div style={{ color: 'var(--text-secondary)' }}>
                        1주당 ≈ <b>{formatKRW(row.price * (row.exchangeRate || usdKrw))}</b>
                        {row.quantity > 0 && (
                          <span> | 총액: <b>{formatUSD(row.quantity * row.price)}</b> (≈ {formatKRW(row.quantity * row.price * (row.exchangeRate || usdKrw))})</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            <button className="btn btn-secondary btn-sm btn-block" onClick={addSellRow}>
              <Plus size={14} /> 매도 추가
            </button>
          </div>
        </div>

        {/* Batch Save Button */}
        <button
          className="btn btn-primary btn-block"
          style={{ padding: '12px', fontSize: '1rem' }}
          onClick={handleSaveBatchTrades}
          disabled={savingBatch}
        >
          <Save size={18} />
          {savingBatch ? '일괄 매매 저장 중...' : '💾 위 내역 전체 일괄 저장'}
        </button>
      </div>
    </>
  );
}
