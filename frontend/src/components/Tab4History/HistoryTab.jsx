/**
 * 탭 5. 매매 및 입출금 기록 관리 컴포넌트 (HistoryTab.jsx)
 * ===============================================
 * 수동 매매 내역(매수/매도)의 일괄 입력 및 체결 기록을 수행하고,
 * 과거 거래 내역의 다차원 필터링 조회 및 일괄 삭제(평단가 자동 롤백)를 지원합니다.
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';

import { api } from '../../utils/api';
import {refreshBookkeeping} from '../../utils/bookkeepingRefresh';
import {readPendingRequest,requireBookkeepingProtocol,singleSubmission} from '../../utils/bookkeepingRequest';

import { loadAccountHoldings } from '../../utils/accountHoldings';
import PriceReference from './PriceReference';
import TradeBatchForm from './TradeBatchForm';
import ActivityHistory from './ActivityHistory';
import {ClipboardPaste,PenLine,Wallet,History} from 'lucide-react';
import UsdLedgerPanel from './UsdLedgerPanel';
import DepositLedgerPanel from './DepositLedgerPanel';
import NamuhMessageImport from './NamuhMessageImport';
import LedgerCorrectionPanel from './LedgerCorrectionPanel';
import ExternalCashFlowPanel from './ExternalCashFlowPanel';
import InternalTransferForm from './InternalTransferForm';
import {executionRows,executionReferencePrice,seedExecutionPrice} from '../../utils/investmentInput';
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
  executionContext=null, embedded=false, active=true, onExecutionChanged, onExitExecution, onBusyChange, onRecorded, inputScope='', refreshRevision=0,
}) {
  const storage=useMemo(()=>draftStorage(inputScope),[inputScope]);
  const task=executionContext?.step;
  const manualTaskKind=task?.kind==='TRANSFER'?'transfers':task?.kind==='DEPOSIT'?'funds':'trades';
  const referencePrice=executionReferencePrice(task,priceMap,pricesData?.prices,usdKrw);
  const blankTrade=direction=>({id:crypto.randomUUID(),accountId:String(task?.account_id || accounts[0]?.id || ''),
    assetId:task?.kind===direction?String(task.asset_id || ''):'',quantity:0,price:task?.kind===direction?referencePrice:0,exchangeRate:usdKrw});
  // Batch Trade Form State
  const submitLock=useRef(false);
  const [initialDraft] = useState(() => readTradeDraft(storage, currentPortfolioId));
  const [tradeDate, setTradeDate] = useState(initialDraft?.tradeDate || new Date(Date.now() + 9 * 3600000).toISOString().split('T')[0]);
  const [buyRows, setBuyRows] = useState(()=>seedExecutionPrice(initialDraft?.buyRows.length ? initialDraft.buyRows : [blankTrade('BUY')],task?.kind==='BUY'?task:null,referencePrice,{pending:Boolean(initialDraft?.pendingSubmission || initialDraft?.uncertainSubmission)}));
  const [sellRows, setSellRows] = useState(()=>seedExecutionPrice(initialDraft?.sellRows.length ? initialDraft.sellRows : [blankTrade('SELL')],task?.kind==='SELL'?task:null,referencePrice,{pending:Boolean(initialDraft?.pendingSubmission || initialDraft?.uncertainSubmission)}));
  const restoredAmounts=Boolean(initialDraft && [...initialDraft.buyRows,...initialDraft.sellRows].some(row=>Number(row.quantity) || Number(row.price)));
  const [draftReviewed, setDraftReviewed] = useState(!restoredAmounts || Boolean(initialDraft?.pendingSubmission));
  const [pendingSubmission,setPendingSubmission]=useState(initialDraft?.pendingSubmission || null);
  const [uncertainSubmission, setUncertainSubmission] = useState(Boolean(initialDraft?.uncertainSubmission));
  const [draftStorageError, setDraftStorageError] = useState(false);
  const [savingBatch, setSavingBatch] = useState(false);
  useEffect(() => {
    if (!savingBatch) setDraftStorageError(!writeTradeDraft(storage, currentPortfolioId, { tradeDate, buyRows, sellRows, uncertainSubmission, pendingSubmission }));
  }, [currentPortfolioId, tradeDate, buyRows, sellRows, savingBatch, uncertainSubmission, pendingSubmission, storage]);
  const clearDraft = () => {
    if (!window.confirm('입력 중인 매수·매도 행을 모두 비울까요? 저장된 장부는 변경되지 않습니다.')) return;
    const blank = () => ({ id: crypto.randomUUID(), accountId: String(accounts[0]?.id || ''), assetId: '', quantity: 0, price: 0, exchangeRate: usdKrw });
    setBuyRows([embedded?blankTrade('BUY'):blank()]); setSellRows([embedded?blankTrade('SELL'):blank()]); setDraftReviewed(true); setUncertainSubmission(false);
  };
  const [usdLedgers, setUsdLedgers] = useState(null);
  const [ledgerError, setLedgerError] = useState('');
  const ledgerScope = useRef(currentPortfolioId);
  useEffect(() => {
    let cancelled = false;
    if(!active)return;
    if (ledgerScope.current !== currentPortfolioId) setUsdLedgers(null);
    ledgerScope.current = currentPortfolioId;
    setLedgerError('');
    api.getUsdLedgers(currentPortfolioId).then(res => { if (!cancelled) setUsdLedgers(res.ledgers); })
      .catch(error => { if (!cancelled) setLedgerError(error.message); });
    return () => { cancelled = true; };
  }, [currentPortfolioId, accounts,active]);
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
  const effectiveView=embedded?'input':view;
  const [reviewCorrection,setReviewCorrection]=useState(null);
  const [noticeCorrection,setNoticeCorrection]=useState(null);
  const [correctionResult,setCorrectionResult]=useState(null);
  const [correctionReset,setCorrectionReset]=useState(null);
  const correctionCompleted=useCallback(result=>{setCorrectionResult(result);setNoticeCorrection(null);},[]);
  const [method,setMethod]=useState(()=>{
    if(embedded && pendingSubmission)return 'manual';
    if(embedded && readPendingRequest(`manual-forex/v1/${currentPortfolioId}`,storage))return 'usd';
    if(embedded && (readPendingRequest(`manual-transfer/v1/${currentPortfolioId}`,storage) || readPendingRequest(`manual-funds/v1/${currentPortfolioId}`,storage)))return 'manual';
    if(embedded)return task?.currency==='USD' && ['BUY','SELL'].includes(task.kind)?'manual':'nh';
    return pendingSubmission || readPendingRequest(`manual-transfer/v1/${currentPortfolioId}`,storage) || readPendingRequest(`manual-funds/v1/${currentPortfolioId}`,storage) || readPendingRequest(`manual-deposit/v1/${currentPortfolioId}`,storage)?'manual':readPendingRequest(`manual-forex/v1/${currentPortfolioId}`,storage)?'usd':'nh';
  });
  const [manualKind,setManualKind]=useState(()=>embedded?manualTaskKind:readPendingRequest(`manual-transfer/v1/${currentPortfolioId}`,storage)?'transfers':readPendingRequest(`manual-funds/v1/${currentPortfolioId}`,storage)?'funds':readPendingRequest(`manual-deposit/v1/${currentPortfolioId}`,storage)?'deposits':'trades');
  const manualMode=()=>{setMethod(embedded && task?.kind==='EXCHANGE_IN'?'usd':'manual');if(embedded)setManualKind(manualTaskKind);};
  const [recordRevision,setRecordRevision]=useState(0);
  useEffect(()=>{setRecordRevision(n=>n+1);},[refreshRevision]);
  useEffect(()=>()=>onBusyChange?.(false),[onBusyChange]);
  const [childBusy,setChildBusy]=useState({nh:false,usd:false,history:false,correction:false,funds:false,deposits:false});
  const [childWriting,setChildWriting]=useState({});
  const nhBusy=useCallback((value,writing=value)=>{setChildBusy(old=>({...old,nh:value}));setChildWriting(old=>({...old,nh:writing}));},[]);
  const usdBusy=useCallback((value,writing=value)=>{setChildBusy(old=>({...old,usd:value}));setChildWriting(old=>({...old,usd:writing}));},[]);
  const fundsBusy=useCallback((value,writing=value)=>{setChildBusy(old=>({...old,funds:value}));setChildWriting(old=>({...old,funds:writing}));},[]);
  const transfersBusy=useCallback((value,writing=value)=>{setChildBusy(old=>({...old,transfers:value}));setChildWriting(old=>({...old,transfers:writing}));},[]);
  const depositsBusy=useCallback((value,writing=value)=>{setChildBusy(old=>({...old,deposits:value}));setChildWriting(old=>({...old,deposits:writing}));},[]);
  const historyBusy=useCallback((value,writing=value)=>{setChildBusy(old=>({...old,history:value}));setChildWriting(old=>({...old,history:writing}));},[]);
  const correctionBusy=useCallback((value,writing=value)=>{setChildBusy(old=>({...old,correction:value}));setChildWriting(old=>({...old,correction:writing}));},[]);
  const navigationBusy=savingBatch || performance?.busy || Object.values(childWriting).some(Boolean);
  const busy=savingBatch || Boolean(pendingSubmission) || performance?.busy || Object.values(childBusy).some(Boolean);
  useEffect(()=>{onBusyChange?.(navigationBusy);},[navigationBusy,onBusyChange]);
  // Load account holdings for sell validation
  useEffect(() => {
    let cancelled = false;
    if(!active)return;
    setAccountHoldingsMap({});
    setHoldingsError(false);
    loadAccountHoldings(accounts, currentPortfolioId, api.getAllHoldings).then((grouped) => {
      if (!cancelled) setAccountHoldingsMap(grouped);
    }).catch(() => {
      if (!cancelled) setHoldingsError(true);
    });
    // Discard a response from a previous portfolio or account refresh.
    return () => { cancelled = true; };
  }, [accounts, currentPortfolioId,active]);

  const loadTrades=useCallback(async()=>{setRecordRevision(n=>n+1);},[]);
  // A manual cash flow already runs inside the performance queue.
  // Do not enqueue and await another job behind that same running job.
  const changed=async({performanceManaged=false}={})=>{await refreshBookkeeping({
    '달러 원가':refreshLedgers,'기록 목록':loadTrades,'자산 현황':onSaved,
    '투자 진행':onExecutionChanged,
    '기간 성과':performance && !performanceManaged?()=>performance.run(performance.capture):undefined,
  });onRecorded?.();};
  // Add/Remove Buy Row
  const addBuyRow = () => {
    setBuyRows((prev) => [
      ...prev,
      blankTrade('BUY')
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
      blankTrade('SELL')
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
    if (pendingSubmission) { await submitManual(pendingSubmission); return; }
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

    let allTrades = [...validBuys, ...validSells];
    try{allTrades=executionRows(allTrades.map(row=>({...row,kind:row.trade_type})),executionContext).map(({kind:_kind,...row})=>row);}catch(error){alert(error.message);return;}
    if (allTrades.length === 0) {
      alert('유효한 매수/매도 내역이 없습니다.');
      return;
    }

    await submitManual({request_id:crypto.randomUUID(),portfolio_id:currentPortfolioId,
      trade_date:tradeDate,trades:allTrades});
  };

  const submitManual = async payload => {
    return singleSubmission(submitLock,async()=>{
      try{await requireBookkeepingProtocol(api);}catch(error){alert(error.message);return;}
      const draft={tradeDate,buyRows,sellRows,uncertainSubmission:true,pendingSubmission:payload};
      if (!writeTradeDraft(storage,currentPortfolioId,draft)) {
        setDraftStorageError(true);alert('임시 저장을 사용할 수 없어 요청을 보내지 않았습니다. 브라우저 저장소를 허용해주세요.');return;
      }
      setPendingSubmission(payload);setSavingBatch(true);
      let recorded=false;
      try {
        const res=await api.batchExecuteTrades(payload);recorded=true;
        const submitted=[...buyRows.filter(r=>r.accountId && r.assetId && r.quantity>0 && r.price>0),
          ...sellRows.filter(r=>r.accountId && r.assetId && r.quantity>0 && r.price>0)];
        const remaining=remainingTradeRows(buyRows,sellRows,submitted,res.results);
        writeTradeDraft(storage,currentPortfolioId,{tradeDate,...remaining,uncertainSubmission:false,pendingSubmission:null});
        const blank=()=>({id:crypto.randomUUID(),accountId:String(accounts[0]?.id || ''),assetId:'',quantity:0,price:0,exchangeRate:usdKrw});
        setBuyRows(remaining.buyRows.length?remaining.buyRows:[blank()]);
        setSellRows(remaining.sellRows.length?remaining.sellRows:[blank()]);
        setPendingSubmission(null);setUncertainSubmission(false);setDraftReviewed(true);
        alert(res.message);await changed();
      } catch(error) {
        if(recorded) alert(`저장은 완료됐지만 ${error.message}`);
        else if(error.status && error.status<500 && ![401,403,429].includes(error.status)) {
          setPendingSubmission(null);setUncertainSubmission(false);setDraftReviewed(true);
          writeTradeDraft(storage,currentPortfolioId,{tradeDate,buyRows,sellRows,uncertainSubmission:false,pendingSubmission:null});
          alert(error.message);
        } else {setUncertainSubmission(true);alert('저장 결과를 확인하지 못했습니다. 같은 요청의 결과 다시 확인 버튼을 사용해주세요. '+error.message);}
      } finally {setSavingBatch(false);}
    });
  };


  return (
    <div className="history-workspace">
      {!embedded && <div className="history-heading"><h2>매매 및 입출금 기록</h2><span className="history-muted">입력한 내용은 최종 반영 전까지 장부를 변경하지 않습니다.</span></div>}
      {!embedded && <div className="history-view-tabs" role="tablist" aria-label="5번 탭 작업">
        <button id="history-input-tab" type="button" role="tab" aria-selected={effectiveView==='input'} aria-controls="history-input-panel" disabled={navigationBusy} onClick={()=>setView('input')}>기록 입력</button>
        <button id="history-record-tab" type="button" role="tab" aria-selected={effectiveView==='records'} aria-controls="history-record-panel" disabled={navigationBusy} onClick={()=>setView('records')}><History size={16}/>기록 조회</button>
      </div>}
      {embedded && <p className="execution-save-note">저장하면 5번 장부에 기록되고 이번 투자 회차의 실행 실적에 함께 반영됩니다.</p>}
      <div id={embedded?'execution-input-panel':'history-input-panel'} role={embedded?undefined:'tabpanel'} aria-labelledby={embedded?undefined:'history-input-tab'} hidden={effectiveView!=='input'}>
        <div className="history-methods" aria-label="입력 방법">
          {(embedded?[['nh','체결 알림 붙여넣기',ClipboardPaste],['manual','직접 입력',PenLine]]:[['nh','NH 알림 가져오기',ClipboardPaste],['manual','직접 입력',PenLine],['usd','달러 관리',Wallet]]).filter(([id])=>!(embedded && id==='nh' && task?.currency==='USD' && ['BUY','SELL'].includes(task.kind))).map(([id,label,Icon])=><button key={id} className="btn btn-secondary" type="button" aria-pressed={method===id || (embedded && method==='usd' && id==='manual')} disabled={navigationBusy} onClick={()=>id==='manual'?manualMode():setMethod(id)}><Icon size={16}/>{embedded && !['BUY','SELL'].includes(task?.kind) && id==='nh'?'NH 알림 붙여넣기':label}</button>)}
        </div>
        {ledgerError && method!=='usd' && <p role="alert">달러 원가 조회 실패: {ledgerError}</p>}
        <div hidden={method!=='nh'}>
          <NamuhMessageImport key={currentPortfolioId} accounts={accounts} assets={assets} portfolioId={currentPortfolioId}
            tradeDate={tradeDate} buyRows={buyRows} disabled={busy && !childBusy.nh} ledgers={usdLedgers} focused
            onDraftCleared={()=>{setNoticeCorrection(null);setCorrectionResult(null);setCorrectionReset(crypto.randomUUID());}} correctionResult={correctionResult?.source?.portfolioId===currentPortfolioId?correctionResult:null} onCorrectionRequest={draft=>{setReviewCorrection(null);setNoticeCorrection({...draft,key:crypto.randomUUID()});if(embedded)onExitExecution?.();}} active={active && effectiveView==='input' && method==='nh'} onBusyChange={nhBusy} executionContext={executionContext} inputScope={inputScope} onChanged={changed}/>
        </div>
        <div hidden={method!=='manual'}>
          {!embedded && <div className="history-inline-choice" aria-label="직접 입력 종류">
            <button type="button" aria-pressed={manualKind==='trades'} disabled={navigationBusy} onClick={()=>setManualKind('trades')}>매수·매도</button>
            <button type="button" aria-pressed={manualKind==='funds'} disabled={navigationBusy} onClick={()=>setManualKind('funds')}>외부 입출금</button>
            <button type="button" aria-pressed={manualKind==='transfers'} disabled={navigationBusy} onClick={()=>setManualKind('transfers')}>계좌 이체</button>
            <button type="button" aria-pressed={manualKind==='deposits'} disabled={navigationBusy} onClick={()=>setManualKind('deposits')}>예금 장부</button>
          </div>}
          {(!embedded || manualKind==='trades') && <div hidden={manualKind!=='trades'}>
            <div className="history-draft-strip">
              <span className="history-muted">매매 입력은 이 기기에 30일간 임시 저장됩니다.</span>
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={clearDraft}>임시 입력 비우기</button>
              {draftStorageError && <p role="alert">임시 저장을 사용할 수 없습니다. 화면을 닫으면 입력이 사라질 수 있습니다.</p>}
              {(restoredAmounts || uncertainSubmission) && <label className="history-check"><input type="checkbox" checked={draftReviewed} disabled={busy} onChange={e=>setDraftReviewed(e.target.checked)}/>복원된 날짜·계좌·입력 내용과 장부 중복 여부를 확인했습니다.</label>}
              {uncertainSubmission && !pendingSubmission && <p role="alert">직전 저장 결과가 불확실합니다. 기록 조회에서 이미 반영된 거래를 확인해주세요.</p>}
              {pendingSubmission && <div role="alert"><p>저장 확인 중인 매매는 내용을 변경하지 않고 같은 요청으로 확인합니다.</p><button type="button" className="btn btn-primary" disabled={savingBatch} onClick={()=>submitManual(pendingSubmission)}>같은 요청의 결과 다시 확인</button></div>}
            </div>
            <TradeBatchForm tradeDate={tradeDate} setTradeDate={setTradeDate} buyRows={buyRows} assets={embedded?assets.filter(a=>String(a.id)===String(task?.asset_id)):assets}
              updateBuyRow={updateBuyRow} accounts={embedded?accounts.filter(a=>String(a.id)===String(task?.account_id)):accounts} removeBuyRow={removeBuyRow} usdKrw={usdKrw} addBuyRow={addBuyRow}
              sellRows={sellRows} holdingsError={holdingsError} accountHoldingsMap={accountHoldingsMap} updateSellRow={updateSellRow}
              removeSellRow={removeSellRow} addSellRow={addSellRow} handleSaveBatchTrades={handleSaveBatchTrades}
              savingBatch={savingBatch} disabled={busy && !savingBatch} usdLedgers={usdLedgers || []} executionStep={task} focused/>
            {!embedded && <PriceReference setIsPriceRefOpen={setIsPriceRefOpen} isPriceRefOpen={isPriceRefOpen}
              assets={assets} usdPriceMap={usdPriceMap} priceMap={priceMap} usdKrw={usdKrw}/>}
          </div>}
          {(!embedded || manualKind==='funds') && <div hidden={manualKind!=='funds'}>{performance && <ExternalCashFlowPanel key={currentPortfolioId}
            portfolioId={currentPortfolioId} accounts={accounts} performance={performance} onOpenAnalysis={onOpenAnalysis}
            disabled={busy && !performance?.busy && !childBusy.funds} onBusyChange={fundsBusy} executionContext={executionContext} inputScope={inputScope} focused onCashChanged={()=>changed({performanceManaged:true})}/>}</div>}
          {(!embedded || manualKind==='transfers') && <div hidden={manualKind!=='transfers'}><InternalTransferForm portfolioId={currentPortfolioId} accounts={accounts} onChanged={changed} onBusyChange={transfersBusy} disabled={busy && !childBusy.transfers} executionContext={executionContext} inputScope={inputScope}/></div>}
          {!embedded && <div hidden={manualKind!=='deposits'}>{<DepositLedgerPanel active={active && effectiveView==='input' && method==='manual' && manualKind==='deposits'} key={currentPortfolioId} portfolioId={currentPortfolioId} assets={assets} onChanged={changed} onBusyChange={depositsBusy} disabled={busy && !childBusy.deposits}/>}</div>}
        </div>
        {(!embedded || task?.kind==='EXCHANGE_IN') && <div hidden={method!=='usd'}>
          {usdLedgers!==null?<UsdLedgerPanel key={currentPortfolioId} accounts={accounts} assets={assets} flows={performance?.data?.flows || []} ledgers={usdLedgers}
            portfolioId={currentPortfolioId} disabled={busy && !childBusy.usd} focused active={active && effectiveView==='input' && method==='usd'} onBusyChange={usdBusy} executionContext={executionContext} inputScope={inputScope} onChanged={changed}/>:<p>달러 원가 조회 중…</p>}
          {ledgerError && <p role="alert">{ledgerError}</p>}
        </div>}

        {!embedded && <LedgerCorrectionPanel hidden={embedded} key={currentPortfolioId} portfolioId={currentPortfolioId} accounts={accounts} assets={assets}
          resetRequest={correctionReset} noticeRequest={noticeCorrection?.source?.portfolioId===currentPortfolioId?noticeCorrection:null} onNoticeSettled={correctionCompleted}
          reviewRequest={reviewCorrection?.portfolioId===currentPortfolioId?reviewCorrection:null} active={active && !embedded && effectiveView==='input'} disabled={busy && !childBusy.correction} onBusyChange={correctionBusy} onChanged={changed}/>}
      </div>
      {!embedded && <div id="history-record-panel" role="tabpanel" aria-labelledby="history-record-tab" hidden={effectiveView!=='records'}>
        <ActivityHistory key={currentPortfolioId} portfolioId={currentPortfolioId} accounts={accounts} assets={assets}
          onReviewCorrection={id=>{setNoticeCorrection(null);setReviewCorrection({id,portfolioId:currentPortfolioId});setView('input');}} active={active && effectiveView==='records'} revision={recordRevision} onBusyChange={historyBusy} onChanged={changed}/>
      </div>}
    </div>
  );
}
