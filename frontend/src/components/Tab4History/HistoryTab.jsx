/**
 * 탭 4. 매매 기록 관리 컴포넌트 (HistoryTab.jsx)
 * ===============================================
 * 수동 매매 내역(매수/매도)의 일괄 입력 및 체결 기록을 수행하고,
 * 과거 거래 내역의 다차원 필터링 조회 및 일괄 삭제(평단가 자동 롤백)를 지원합니다.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Plus, Trash2, ChevronDown, ChevronUp, Save } from 'lucide-react';
import { api } from '../../utils/api';
import { formatKRW, formatUSD, formatQuantity } from '../../utils/formatters';

export default function HistoryTab({ assets, accounts, priceMap, usdKrw = 1380.0, pricesData, onSaved, currentPortfolioId = 'default' }) {
  // Batch Trade Form State
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().split('T')[0]);
  const [buyRows, setBuyRows] = useState([{ id: '1', accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
  const [sellRows, setSellRows] = useState([{ id: '1', accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
  const [savingBatch, setSavingBatch] = useState(false);

  // Price map lookup for USD native prices
  const usdPriceMap = useMemo(() => {
    const map = {};
    if (pricesData?.prices) {
      pricesData.prices.forEach((p) => {
        if (p.price_usd) map[String(p.id)] = p.price_usd;
      });
    }
    return map;
  }, [pricesData]);

  // Account Holdings Map for Sell Validation
  const [accountHoldingsMap, setAccountHoldingsMap] = useState({});

  // Reference Prices Collapsible
  const [isPriceRefOpen, setIsPriceRefOpen] = useState(false);

  // Trade History Table & Filters
  const [trades, setTrades] = useState([]);
  const [loadingTrades, setLoadingTrades] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [selectedAccFilter, setSelectedAccFilter] = useState('all');
  const [selectedAssetFilter, setSelectedAssetFilter] = useState('all');
  const [selectedTradeIds, setSelectedTradeIds] = useState([]);
  const [deletingTrades, setDeletingTrades] = useState(false);

  // Load account holdings for sell validation
  useEffect(() => {
    accounts.forEach((acc) => {
      api.getAccountHoldings(acc.id).then((res) => {
        setAccountHoldingsMap((prev) => ({
          ...prev,
          [String(acc.id)]: res.holdings || []
        }));
      });
    });
  }, [accounts]);

  // Load trade history
  const loadTrades = useCallback(async () => {
    setLoadingTrades(true);
    try {
      const params = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      if (selectedAccFilter !== 'all') params.account_id = selectedAccFilter;
      if (selectedAssetFilter !== 'all') params.asset_id = selectedAssetFilter;
      if (currentPortfolioId && currentPortfolioId !== 'all') params.portfolio_id = currentPortfolioId;

      const res = await api.getTrades(params);
      setTrades(res.trades || []);
      setSelectedTradeIds([]);
    } catch (err) {
      console.error('Failed to load trades:', err);
    } finally {
      setLoadingTrades(false);
    }
  }, [startDate, endDate, selectedAccFilter, selectedAssetFilter, currentPortfolioId]);

  useEffect(() => {
    loadTrades();
  }, [loadTrades]);

  // Add/Remove Buy Row
  const addBuyRow = () => {
    setBuyRows((prev) => [
      ...prev,
      { id: Date.now().toString(), accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }
    ]);
  };

  const removeBuyRow = (id) => {
    if (buyRows.length <= 1) return;
    setBuyRows((prev) => prev.filter((r) => r.id !== id));
  };

  const updateBuyRow = (id, field, value) => {
    setBuyRows((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r;
        const updated = { ...r, [field]: value };
        if (field === 'assetId' && value) {
          const ast = assets.find((a) => String(a.id) === String(value));
          if (ast?.market === 'US') {
            updated.price = usdPriceMap[String(value)] || (priceMap[String(value)] ? Number((priceMap[String(value)] / (usdKrw || 1380)).toFixed(2)) : 0);
            updated.exchangeRate = r.exchangeRate || usdKrw;
          } else {
            updated.price = priceMap[String(value)] || 0;
            updated.exchangeRate = 1.0;
          }
        }
        return updated;
      })
    );
  };

  // Add/Remove Sell Row
  const addSellRow = () => {
    setSellRows((prev) => [
      ...prev,
      { id: Date.now().toString(), accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }
    ]);
  };

  const removeSellRow = (id) => {
    if (sellRows.length <= 1) return;
    setSellRows((prev) => prev.filter((r) => r.id !== id));
  };

  const updateSellRow = (id, field, value) => {
    setSellRows((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r;
        const updated = { ...r, [field]: value };
        if (field === 'assetId' && value) {
          const ast = assets.find((a) => String(a.id) === String(value));
          if (ast?.market === 'US') {
            updated.price = usdPriceMap[String(value)] || (priceMap[String(value)] ? Number((priceMap[String(value)] / (usdKrw || 1380)).toFixed(2)) : 0);
            updated.exchangeRate = r.exchangeRate || usdKrw;
          } else {
            updated.price = priceMap[String(value)] || 0;
            updated.exchangeRate = 1.0;
          }
        }
        return updated;
      })
    );
  };

  // Submit Batch Trades
  const handleSaveBatchTrades = async () => {
    const validBuys = buyRows
      .filter((r) => r.accountId && r.assetId && r.quantity > 0 && r.price > 0)
      .map((r) => {
        const ast = assets.find((a) => String(a.id) === String(r.assetId));
        const isUS = ast?.market === 'US';
        return {
          account_id: String(r.accountId),
          asset_id: String(r.assetId),
          trade_type: 'BUY',
          quantity: Number(r.quantity),
          price: Number(r.price),
          currency: isUS ? 'USD' : 'KRW',
          exchange_rate: isUS ? Number(r.exchangeRate || usdKrw) : 1.0
        };
      });

    const validSells = sellRows
      .filter((r) => r.accountId && r.assetId && r.quantity > 0 && r.price > 0)
      .map((r) => {
        const ast = assets.find((a) => String(a.id) === String(r.assetId));
        const isUS = ast?.market === 'US';
        return {
          account_id: String(r.accountId),
          asset_id: String(r.assetId),
          trade_type: 'SELL',
          quantity: Number(r.quantity),
          price: Number(r.price),
          currency: isUS ? 'USD' : 'KRW',
          exchange_rate: isUS ? Number(r.exchangeRate || usdKrw) : 1.0
        };
      });

    const allTrades = [...validBuys, ...validSells];
    if (allTrades.length === 0) {
      alert('유효한 매수/매도 내역이 없습니다.');
      return;
    }

    setSavingBatch(true);
    try {
      const res = await api.batchExecuteTrades(tradeDate, allTrades);
      alert(res.message || '매매 내역이 성공적으로 저장되었습니다.');
      // Reset form
      setBuyRows([{ id: '1', accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
      setSellRows([{ id: '1', accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
      loadTrades();
      onSaved();
    } catch (err) {
      alert(`저장 실패: ${err.message}`);
    } finally {
      setSavingBatch(false);
    }
  };

  // Toggle Trade Selection for Deletion
  const toggleSelectTrade = (tradeId) => {
    setSelectedTradeIds((prev) =>
      prev.includes(tradeId) ? prev.filter((id) => id !== tradeId) : [...prev, tradeId]
    );
  };

  const toggleSelectAllTrades = () => {
    if (selectedTradeIds.length === trades.length) {
      setSelectedTradeIds([]);
    } else {
      setSelectedTradeIds(trades.map((t) => t.id));
    }
  };

  // Delete Selected Trades (with Rollback)
  const handleDeleteSelectedTrades = async () => {
    if (selectedTradeIds.length === 0) return;
    if (!window.confirm(`선택한 ${selectedTradeIds.length}건의 매매 기록을 삭제하시겠습니까?\n과거 평단가와 수량이 자동으로 재계산되어 복원됩니다.`)) return;

    setDeletingTrades(true);
    try {
      const res = await api.batchDeleteTrades(selectedTradeIds);
      alert(res.message || '삭제 및 평단가 롤백이 완료되었습니다.');
      loadTrades();
      onSaved();
    } catch (err) {
      alert(`삭제 실패: ${err.message}`);
    } finally {
      setDeletingTrades(false);
    }
  };

  return (
    <div>
      {/* 1. Price Reference Collapsible */}
      <div className="section-card" style={{ padding: '16px 20px', marginBottom: '16px' }}>
        <div 
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
          onClick={() => setIsPriceRefOpen(!isPriceRefOpen)}
        >
          <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>💡 실시간 시세 참고표 (현재가 확인용)</span>
          {isPriceRefOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>

        {isPriceRefOpen && (
          <div className="table-container" style={{ marginTop: '14px' }}>
            <table className="custom-table">
              <thead>
                <tr>
                  <th>종목명</th>
                  <th>티커</th>
                  <th>시장</th>
                  <th>실시간 현재가</th>
                  <th>원화 환산가</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((ast) => {
                  const isUS = ast.market === 'US';
                  const usdP = usdPriceMap[String(ast.id)] || (priceMap[String(ast.id)] ? Number((priceMap[String(ast.id)] / (usdKrw || 1380)).toFixed(2)) : 0);
                  const krwP = priceMap[String(ast.id)] || 0;
                  return (
                    <tr key={ast.id}>
                      <td style={{ fontWeight: 600 }}>{isUS ? '🇺🇸 ' : '🇰🇷 '}{ast.name}</td>
                      <td>{ast.ticker}</td>
                      <td>{isUS ? '미국 (USD)' : '국내 (KRW)'}</td>
                      <td style={{ fontWeight: 700 }}>
                        {isUS ? formatUSD(usdP) : formatKRW(krwP)}
                      </td>
                      <td style={{ fontWeight: 600, color: isUS ? 'var(--text-secondary)' : 'inherit' }}>
                        {formatKRW(krwP)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

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
                  🗑️ 선택된 {selectedTradeIds.length}개의 기록 삭제 및 평단가 자동 롤백
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
    </div>
  );
}
