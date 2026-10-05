/**
 * 탭 4. 매매 기록 관리 컴포넌트 (HistoryTab.jsx)
 * ===============================================
 * 수동 매매 내역(매수/매도)의 일괄 입력 및 체결 기록을 수행하고,
 * 과거 거래 내역의 다차원 필터링 조회 및 일괄 삭제(평단가 자동 롤백)를 지원합니다.
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';

import { api } from '../../utils/api';

import { loadAccountHoldings } from '../../utils/accountHoldings';
import PriceReference from './PriceReference';
import TradeBatchForm from './TradeBatchForm';
import TradeHistorySection from './TradeHistorySection';
import UsdLedgerPanel from './UsdLedgerPanel';
import NamuhMessageImport from './NamuhMessageImport';
import { appendNamuhRows } from '../../utils/namuhMessage';

export default function HistoryTab({
  assets,
  accounts,
  priceMap,
  usdKrw = 1380.0,
  pricesData,
  onSaved,
  currentPortfolioId = 'default',
}) {
  // Batch Trade Form State
  const [tradeDate, setTradeDate] = useState(new Date(Date.now() + 9 * 3600000).toISOString().split('T')[0]);
  const [buyRows, setBuyRows] = useState([{ id: '1', accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
  const [sellRows, setSellRows] = useState([{ id: '1', accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
  const [savingBatch, setSavingBatch] = useState(false);
  const [usdLedgers, setUsdLedgers] = useState(null);
  const [ledgerError, setLedgerError] = useState('');
  const ledgerScope = useRef(currentPortfolioId);
  useEffect(() => {
    let cancelled = false;
    if (ledgerScope.current !== currentPortfolioId) setUsdLedgers(null);
    ledgerScope.current = currentPortfolioId;
    setLedgerError('');
    api.getUsdLedgers(currentPortfolioId).then(res => { if (!cancelled) setUsdLedgers(res.ledgers); })
      .catch(error => { if (!cancelled) setLedgerError(error.message); });
    return () => { cancelled = true; };
  }, [currentPortfolioId, accounts]);
  const refreshLedgers = async () => {
    const res = await api.getUsdLedgers(currentPortfolioId);
    setUsdLedgers(res.ledgers);
  };

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
  const [holdingsError, setHoldingsError] = useState(false);

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
    let cancelled = false;
    setAccountHoldingsMap({});
    setHoldingsError(false);
    loadAccountHoldings(accounts, currentPortfolioId, api.getAllHoldings).then((grouped) => {
      if (!cancelled) setAccountHoldingsMap(grouped);
    }).catch(() => {
      if (!cancelled) setHoldingsError(true);
    });
    // Discard a response from a previous portfolio or account refresh.
    return () => { cancelled = true; };
  }, [accounts, currentPortfolioId]);

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
    if (buyRows.length <= 1) {
      if (buyRows[0]?.importSource) setBuyRows([{ id: crypto.randomUUID(), accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
      return;
    }
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
    if (buyRows.some(r => r.importSource && r.importDate !== tradeDate)) {
      alert('가져온 거래의 체결일자가 다릅니다. 해당 행을 삭제한 뒤 올바른 날짜로 다시 가져오세요.');
      return;
    }
    if (buyRows.some(r => r.importSource && (!accounts.some(a => String(a.id) === r.accountId)
      || !assets.some(a => String(a.id) === r.assetId && a.market === 'KR' && !a.is_deposit
        && (a.allowed_accounts || []).map(String).includes(r.accountId))))) {
      alert('가져온 거래의 계좌와 종목을 현재 포트폴리오에서 다시 확인해주세요.');
      return;
    }
    const submittedBuys = buyRows.filter((r) => r.accountId && r.assetId && r.quantity > 0 && r.price > 0);
    const submittedSells = sellRows.filter((r) => r.accountId && r.assetId && r.quantity > 0 && r.price > 0);
    const validBuys = submittedBuys
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
          exchange_rate: isUS ? Number(r.exchangeRate || usdKrw) : 1.0,
          ...(r.importSource ? { import_source: r.importSource, broker_order_no: r.brokerOrderNo } : {})
        };
      });

    const validSells = submittedSells
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
      alert([res.message || '매매 내역이 성공적으로 저장되었습니다.', ...(res.errors || [])].join('\n'));
      // Keep failed rows for correction, removing only confirmed successful requests.
      const successful = new Set((res.results || []).filter(r => r.success).map(r => r.index));
      const submitted = [...submittedBuys, ...submittedSells];
      const completedIds = new Set(submitted.filter((_, index) => successful.has(index)).map(r => r));
      const blank = () => ({ id: Date.now().toString(), accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw });
      setBuyRows(prev => { const remaining = prev.filter(r => !completedIds.has(r)); return remaining.length ? remaining : [blank()]; });
      setSellRows(prev => { const remaining = prev.filter(r => !completedIds.has(r)); return remaining.length ? remaining : [blank()]; });
      loadTrades();
      await refreshLedgers();
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
    if (!window.confirm(`선택한 ${selectedTradeIds.length}건의 매매 기록을 삭제하시겠습니까?\n예수금 변동을 되돌리고 보유 수량과 매입원가를 재계산합니다.`)) return;

    setDeletingTrades(true);
    try {
      const res = await api.batchDeleteTrades(selectedTradeIds);
      alert(res.message || '삭제 및 예수금·보유 잔고 복원이 완료되었습니다.');
      loadTrades();
      await refreshLedgers();
      onSaved();
    } catch (err) {
      alert(`삭제 실패: ${err.message}`);
    } finally {
      setDeletingTrades(false);
    }
  };

  return (
    <div>
      {usdLedgers !== null && <UsdLedgerPanel key={currentPortfolioId} accounts={accounts} assets={assets} ledgers={usdLedgers} portfolioId={currentPortfolioId}
        onChanged={async () => { await refreshLedgers(); loadTrades(); onSaved(); }} />}
      {ledgerError && <p role="alert">달러 원가 조회 실패: {ledgerError}</p>}
      <PriceReference
        setIsPriceRefOpen={setIsPriceRefOpen}
        isPriceRefOpen={isPriceRefOpen}
        assets={assets}
        usdPriceMap={usdPriceMap}
        priceMap={priceMap}
        usdKrw={usdKrw}
      />

      <NamuhMessageImport key={currentPortfolioId} accounts={accounts} assets={assets} portfolioId={currentPortfolioId}
        tradeDate={tradeDate} buyRows={buyRows} disabled={savingBatch}
        onAppend={drafts => setBuyRows(appendNamuhRows(buyRows, drafts, tradeDate))} />

      <TradeBatchForm
        tradeDate={tradeDate}
        setTradeDate={setTradeDate}
        buyRows={buyRows}
        assets={assets}
        updateBuyRow={updateBuyRow}
        accounts={accounts}
        removeBuyRow={removeBuyRow}
        usdKrw={usdKrw}
        addBuyRow={addBuyRow}
        sellRows={sellRows}
        holdingsError={holdingsError}
        accountHoldingsMap={accountHoldingsMap}
        updateSellRow={updateSellRow}
        removeSellRow={removeSellRow}
        addSellRow={addSellRow}
        handleSaveBatchTrades={handleSaveBatchTrades}
        savingBatch={savingBatch}
        usdLedgers={usdLedgers || []}
      />

      <TradeHistorySection
        startDate={startDate}
        setStartDate={setStartDate}
        endDate={endDate}
        setEndDate={setEndDate}
        selectedAccFilter={selectedAccFilter}
        setSelectedAccFilter={setSelectedAccFilter}
        accounts={accounts}
        selectedAssetFilter={selectedAssetFilter}
        setSelectedAssetFilter={setSelectedAssetFilter}
        assets={assets}
        loadingTrades={loadingTrades}
        trades={trades}
        selectedTradeIds={selectedTradeIds}
        toggleSelectAllTrades={toggleSelectAllTrades}
        toggleSelectTrade={toggleSelectTrade}
        handleDeleteSelectedTrades={handleDeleteSelectedTrades}
        deletingTrades={deletingTrades}
      />

    </div>
  );
}
