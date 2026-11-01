import React from 'react';

/** Shared controlled fields; both layouts use the same row and callbacks. */
export default function TradeRowInputs({row,accounts,assetOptions,assetPlaceholder,isUS,onUpdate,onRemove}) {
  return <>
                  {/* Desktop Layout */}
                  <div className="trade-row-desktop">
                    <select
                      className="input-select"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.accountId}
                      onChange={(e) => onUpdate(row.id, 'accountId', e.target.value)}
                    >
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>
                      ))}
                    </select>

                    <select
                      className="input-select"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.assetId}
                      onChange={(e) => onUpdate(row.id, 'assetId', e.target.value)}
                    >
                      <option value="">{assetPlaceholder}</option>
                      {assetOptions}
                    </select>

                    <input
                      type="number"
                      placeholder="수량"
                      className="input-number"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.quantity || ''}
                      onChange={(e) => onUpdate(row.id, 'quantity', parseFloat(e.target.value) || 0)}
                      min={0}
                      step={1}
                    />

                    <input
                      type="number"
                      placeholder={isUS ? '단가($ USD)' : '단가(원)'}
                      className="input-number"
                      style={{ fontSize: '0.82rem', padding: '6px' }}
                      value={row.price || ''}
                      onChange={(e) => onUpdate(row.id, 'price', parseFloat(e.target.value) || 0)}
                      min={0}
                      step={isUS ? 0.01 : 100}
                    />

                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ padding: '6px 8px' }}
                      onClick={() => onRemove(row.id)}
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
                        onChange={(e) => onUpdate(row.id, 'accountId', e.target.value)}
                      >
                        {accounts.map((a) => (
                          <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>
                        ))}
                      </select>

                      <select
                        className="input-select"
                        value={row.assetId}
                        onChange={(e) => onUpdate(row.id, 'assetId', e.target.value)}
                      >
                        <option value="">{assetPlaceholder}</option>
                        {assetOptions}
                      </select>
                    </div>

                    <div className="trade-row-mobile-line2">
                      <input
                        type="number"
                        placeholder="수량 (주)"
                        className="input-number"
                        value={row.quantity || ''}
                        onChange={(e) => onUpdate(row.id, 'quantity', parseFloat(e.target.value) || 0)}
                        min={0}
                        step={1}
                      />

                      <input
                        type="number"
                        placeholder={isUS ? '단가 ($ USD)' : '체결단가 (원)'}
                        className="input-number"
                        value={row.price || ''}
                        onChange={(e) => onUpdate(row.id, 'price', parseFloat(e.target.value) || 0)}
                        min={0}
                        step={isUS ? 0.01 : 100}
                      />

                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '8px 12px' }}
                        onClick={() => onRemove(row.id)}
                        title="행 삭제"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

  </>;
}
