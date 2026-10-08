/**
 * 탭 4. 매매 및 입출금 기록 관리 컴포넌트 (HistoryTab.jsx)
 * ===============================================
 * 수동 매매 내역(매수/매도)의 일괄 입력 및 체결 기록을 수행하고,
 * 과거 거래 내역의 다차원 필터링 조회 및 일괄 삭제(평단가 자동 롤백)를 지원합니다.
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';

import { api } from '../../utils/api';

import { loadAccountHoldings } from '../../utils/accountHoldings';
import PriceReference from './PriceReference';
import TradeBatchForm from './TradeBatchForm';
import ActivityHistory from './ActivityHistory';
import {ClipboardPaste,PenLine,Wallet,History} from 'lucide-react';
import UsdLedgerPanel from './UsdLedgerPanel';
import NamuhMessageImport from './NamuhMessageImport';
import ExternalCashFlowPanel from './ExternalCashFlowPanel';
import { readTradeDraft, writeTradeDraft, remainingTradeRows, draftStorage } from '../../utils/tradeDraft';

export default function HistoryTab({
  assets,
  accounts,
  priceMap,
  usdKrw = 1380.0,
  pricesData,
  onSaved,
  currentPortfolioId = 'default',
  performance,
  onOpenAnalysis,
}) {
  // Batch Trade Form State
  const [initialDraft] = useState(() => readTradeDraft(draftStorage(), currentPortfolioId));
  const [tradeDate, setTradeDate] = useState(initialDraft?.tradeDate || new Date(Date.now() + 9 * 3600000).toISOString().split('T')[0]);
  const [buyRows, setBuyRows] = useState(initialDraft?.buyRows.length ? initialDraft.buyRows : [{ id: '1', accountId: String(accounts[0]?.id || ''), assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
  const [sellRows, setSellRows] = useState(initialDraft?.sellRows.length ? initialDraft.sellRows : [{ id: '1', accountId: String(accounts[0]?.id || ''), assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw }]);
  const [draftReviewed, setDraftReviewed] = useState(!initialDraft);
  const [uncertainSubmission, setUncertainSubmission] = useState(Boolean(initialDraft?.uncertainSubmission));
  const [draftStorageError, setDraftStorageError] = useState(false);
  const [savingBatch, setSavingBatch] = useState(false);
  useEffect(() => {
    if (!savingBatch) setDraftStorageError(!writeTradeDraft(draftStorage(), currentPortfolioId, { tradeDate, buyRows, sellRows, uncertainSubmission }));
  }, [currentPortfolioId, tradeDate, buyRows, sellRows, savingBatch, uncertainSubmission]);
  const clearDraft = () => {
    if (!window.confirm('입력 중인 매수·매도 행을 모두 비울까요? 저장된 장부는 변경되지 않습니다.')) return;
    const blank = () => ({ id: crypto.randomUUID(), accountId: String(accounts[0]?.id || ''), assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw });
    setBuyRows([blank()]); setSellRows([blank()]); setDraftReviewed(true); setUncertainSubmission(false);
  };
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
    setUsdLedgers(res.ledgers);setLedgerError('');
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

  const [view,setView]=useState('input');
  const [method,setMethod]=useState('nh');
  const [manualKind,setManualKind]=useState('trades');
  const [recordRevision,setRecordRevision]=useState(0);
  const [childBusy,setChildBusy]=useState({nh:false,usd:false,history:false});
  const nhBusy=useCallback(value=>setChildBusy(old=>({...old,nh:value})),[]);
  const usdBusy=useCallback(value=>setChildBusy(old=>({...old,usd:value})),[]);
  const historyBusy=useCallback(value=>setChildBusy(old=>({...old,history:value})),[]);
  const busy=savingBatch || performance?.busy || Object.values(childBusy).some(Boolean);
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

  const loadTrades=useCallback(async()=>{setRecordRevision(n=>n+1);},[]);
  const changed=async()=>{await refreshLedgers();await loadTrades();await onSaved();
    if(performance)await performance.run(performance.capture);};
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
    if (!draftReviewed) { alert('복원된 입력 내용과 기존 장부의 중복 여부를 먼저 확인해주세요.'); return; }
    if ([...buyRows, ...sellRows].some(r => r.assetId && (!accounts.some(a => String(a.id) === String(r.accountId))
      || !assets.some(a => String(a.id) === String(r.assetId) && (a.allowed_accounts || []).map(String).includes(String(r.accountId)))))) {
      alert('입력 행의 계좌·종목이 현재 포트폴리오에 없거나 허용되지 않습니다. 해당 행을 수정하거나 삭제해주세요.'); return;
    }
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
    // A refresh/network loss during submission must never silently retry manual rows.
    writeTradeDraft(draftStorage(), currentPortfolioId, { tradeDate, buyRows, sellRows, uncertainSubmission: true });
    try {
      const res = await api.batchExecuteTrades(tradeDate, allTrades);
      // Keep failed rows for correction, removing only confirmed successful requests.
      const submitted = [...submittedBuys, ...submittedSells];
      const remaining = remainingTradeRows(buyRows, sellRows, submitted, res.results);
      writeTradeDraft(draftStorage(), currentPortfolioId, { tradeDate, ...remaining, uncertainSubmission: false });
      const blank = () => ({ id: Date.now().toString(), accountId: accounts[0]?.id || '', assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw });
      setBuyRows(remaining.buyRows.length ? remaining.buyRows : [blank()]);
      setSellRows(remaining.sellRows.length ? remaining.sellRows : [blank()]);
      setUncertainSubmission(false);
      alert([res.message || '매매 내역이 성공적으로 저장되었습니다.', ...(res.errors || [])].join('\n'));
      loadTrades();
      await refreshLedgers();
      onSaved();
    } catch (err) {
      setUncertainSubmission(true); setDraftReviewed(false);
      alert(`저장 실패: ${err.message}`);
    } finally {
      setSavingBatch(false);
    }
  };

  return (
    <div className="history-workspace">
      <div className="history-heading"><h2>매매 및 입출금 기록</h2><span className="history-muted">입력한 내용은 최종 반영 전까지 장부를 변경하지 않습니다.</span></div>
      <div className="history-view-tabs" role="tablist" aria-label="4번 탭 작업">
        <button id="history-input-tab" type="button" role="tab" aria-selected={view==='input'} aria-controls="history-input-panel" disabled={busy} onClick={()=>setView('input')}>기록 입력</button>
        <button id="history-record-tab" type="button" role="tab" aria-selected={view==='records'} aria-controls="history-record-panel" disabled={busy} onClick={()=>setView('records')}><History size={16}/>기록 조회</button>
      </div>
      <div id="history-input-panel" role="tabpanel" aria-labelledby="history-input-tab" hidden={view!=='input'}>
        <div className="history-methods" aria-label="입력 방법">
          {[['nh','NH 알림 가져오기',ClipboardPaste],['manual','직접 입력',PenLine],['usd','달러 관리',Wallet]].map(([id,label,Icon])=><button key={id} className="btn btn-secondary" type="button" aria-pressed={method===id} disabled={busy} onClick={()=>setMethod(id)}><Icon size={16}/>{label}</button>)}
        </div>
        {ledgerError && method!=='usd' && <p role="alert">달러 원가 조회 실패: {ledgerError}</p>}
        <div hidden={method!=='nh'}>
          <NamuhMessageImport key={currentPortfolioId} accounts={accounts} assets={assets} portfolioId={currentPortfolioId}
            tradeDate={tradeDate} buyRows={buyRows} disabled={busy && !childBusy.nh} ledgers={usdLedgers} focused
            active={view==='input' && method==='nh'} onBusyChange={nhBusy} onChanged={changed}/>
        </div>
        <div hidden={method!=='manual'}>
          <div className="history-inline-choice" aria-label="직접 입력 종류">
            <button type="button" aria-pressed={manualKind==='trades'} disabled={busy} onClick={()=>setManualKind('trades')}>매수·매도</button>
            <button type="button" aria-pressed={manualKind==='funds'} disabled={busy} onClick={()=>setManualKind('funds')}>외부 입출금</button>
          </div>
          <div hidden={manualKind!=='trades'}>
            <div className="history-draft-strip">
              <span className="history-muted">매매 입력은 이 기기에 30일간 임시 저장됩니다.</span>
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={clearDraft}>임시 입력 비우기</button>
              {draftStorageError && <p role="alert">임시 저장을 사용할 수 없습니다. 화면을 닫으면 입력이 사라질 수 있습니다.</p>}
              {(initialDraft || uncertainSubmission) && <label className="history-check"><input type="checkbox" checked={draftReviewed} disabled={busy} onChange={e=>setDraftReviewed(e.target.checked)}/>복원된 날짜·계좌·입력 내용과 장부 중복 여부를 확인했습니다.</label>}
              {uncertainSubmission && <p role="alert">직전 저장 결과가 불확실합니다. 기록 조회에서 이미 반영된 거래를 확인해주세요.</p>}
            </div>
            <TradeBatchForm tradeDate={tradeDate} setTradeDate={setTradeDate} buyRows={buyRows} assets={assets}
              updateBuyRow={updateBuyRow} accounts={accounts} removeBuyRow={removeBuyRow} usdKrw={usdKrw} addBuyRow={addBuyRow}
              sellRows={sellRows} holdingsError={holdingsError} accountHoldingsMap={accountHoldingsMap} updateSellRow={updateSellRow}
              removeSellRow={removeSellRow} addSellRow={addSellRow} handleSaveBatchTrades={handleSaveBatchTrades}
              savingBatch={savingBatch} usdLedgers={usdLedgers || []} focused/>
            <PriceReference setIsPriceRefOpen={setIsPriceRefOpen} isPriceRefOpen={isPriceRefOpen}
              assets={assets} usdPriceMap={usdPriceMap} priceMap={priceMap} usdKrw={usdKrw}/>
          </div>
          <div hidden={manualKind!=='funds'}>{performance && <ExternalCashFlowPanel key={currentPortfolioId}
            portfolioId={currentPortfolioId} accounts={accounts} performance={performance} onOpenAnalysis={onOpenAnalysis}
            focused onCashChanged={async()=>{await refreshLedgers();await loadTrades();await onSaved();}}/>}</div>
        </div>
        <div hidden={method!=='usd'}>
          {usdLedgers!==null?<UsdLedgerPanel key={currentPortfolioId} accounts={accounts} assets={assets} ledgers={usdLedgers}
            portfolioId={currentPortfolioId} focused active={view==='input' && method==='usd'} onBusyChange={usdBusy} onChanged={changed}/>:<p>달러 원가 조회 중…</p>}
          {ledgerError && <p role="alert">{ledgerError}</p>}
        </div>
      </div>
      <div id="history-record-panel" role="tabpanel" aria-labelledby="history-record-tab" hidden={view!=='records'}>
        <ActivityHistory key={currentPortfolioId} portfolioId={currentPortfolioId} accounts={accounts} assets={assets}
          active={view==='records'} revision={recordRevision} onBusyChange={historyBusy} onChanged={changed}/>
      </div>
    </div>
  );
}
