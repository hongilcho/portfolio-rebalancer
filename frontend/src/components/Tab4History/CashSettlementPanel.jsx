import React,{useEffect,useRef,useState} from 'react';
import '../common/TradingFees.css';
import {api} from '../../utils/api';
import {formatKRW,formatUSD} from '../../utils/formatters';
const storageKey=pid=>`cash-settlement/pending/v1/${pid}`;
function restored(pid){try{
  const value=JSON.parse(localStorage.getItem(storageKey(pid)));
  return value&&typeof value.request_id==='string'&&/^[a-f0-9]{64}$/.test(value.token)&&value.confirmed===true&&
    ['COST_SETTLEMENT','BALANCE_SETTLEMENT'].includes(value.proposal?.kind)&&typeof value.proposal?.account_id==='string'?value:null;
}catch{return null;}}

export default function CashSettlementPanel({portfolioId,accounts,disabled=false,onChanged=()=>{},onBusyChange=()=>{},reviewRequest=null,onReturnToInput}){
  const [open,setOpen]=useState(false),[aid,setAid]=useState(''),[currency,setCurrency]=useState('KRW');
  const [balance,setBalance]=useState(''),[classification,setClassification]=useState('BALANCE_SETTLEMENT');
  const [reason,setReason]=useState(''),[rate,setRate]=useState(''),[context,setContext]=useState(null);
  const [preview,setPreview]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const [pending,setPending]=useState(()=>restored(portfolioId));const revision=useRef(0),inFlight=useRef(false),panel=useRef(null);
  const [reviewSource,setReviewSource]=useState(null),[reviewedBalance,setReviewedBalance]=useState(false),[completed,setCompleted]=useState(false);
  const handledReview=useRef(null);
  useEffect(()=>{
    if(!reviewRequest || handledReview.current===reviewRequest.key)return;
    handledReview.current=reviewRequest.key;setOpen(true);
    if(pending){setMessage('저장 결과가 확인되지 않은 정정이 있습니다. 기존 요청의 결과를 먼저 확인해주세요.');return;}
    revision.current++;setReviewSource(reviewRequest);setAid(reviewRequest.accountId);setCurrency('KRW');
    setBalance(reviewRequest.balance==null?'':String(reviewRequest.balance));setClassification('BALANCE_SETTLEMENT');
    setReason(reviewRequest.reason);setRate('');setContext(null);setPreview(null);setMessage('');setCompleted(false);setReviewedBalance(false);
    panel.current?.scrollIntoView?.({behavior:'smooth',block:'start'});
  },[reviewRequest,pending]);
  useEffect(()=>{
    if(!open||!aid)return;let cancelled=false;setContext(null);setPreview(null);setMessage('');
    api.getLedgerAccount(portfolioId,aid).then(v=>{if(!cancelled)setContext(v.state);}).catch(e=>{if(!cancelled)setMessage(e.message);});
    return()=>{cancelled=true;};
  },[open,aid,portfolioId,reviewRequest?.key]);
  const edit=(setter,value)=>{revision.current++;setter(value);setPreview(null);setMessage('');setReviewedBalance(false);setCompleted(false);};
  const run=async(job,writing=false)=>{if(inFlight.current)return;inFlight.current=true;setBusy(true);onBusyChange(true,writing);setMessage('');try{await job();}catch(e){setMessage(e.message);}finally{inFlight.current=false;setBusy(false);onBusyChange(false,false);}};
  const check=()=>run(async()=>{const rev=revision.current;const v=await api.previewCashSettlement(portfolioId,{account_id:aid,currency,balance:Number(balance),classification,reason:reason||'정기 예수금 차이 정산',average_rate:Number(rate)||0});if(revision.current===rev)setPreview(v);});
  const save=()=>run(async()=>{
    const req=pending||{request_id:crypto.randomUUID(),proposal:preview.proposal,token:preview.token,decisions:{},confirmed:true};
    // Persist before sending. Do not send if uncertain results could not be retained.
    localStorage.setItem(storageKey(portfolioId),JSON.stringify(req));setPending(req);
    try{await api.commitLedgerCorrection(portfolioId,req);}catch(e){if(e.status&&e.status<500&&![401,403,429].includes(e.status)){localStorage.removeItem(storageKey(portfolioId));setPending(null);setPreview(null);}throw e;}
    localStorage.removeItem(storageKey(portfolioId));setPending(null);setPreview(null);setBalance('');setContext(null);setCompleted(true);
    setMessage('차이를 정산했습니다. 원래 매매 기록과 과거 성과는 그대로 보존합니다.');
    try{await onChanged();if(aid)setContext((await api.getLedgerAccount(portfolioId,aid)).state);}
    catch{setMessage('정산은 저장됐지만 화면 갱신에 실패했습니다. 다시 정산하지 말고 새로고침해주세요.');}
  },true);
  const shown=pending?.proposal||preview?.proposal;
  const format=shown?.currency==='USD'||(!shown&&currency==='USD')?formatUSD:formatKRW;
  const key=currency==='USD'?'deposit_usd':'deposit_krw';
  return <details ref={panel} className="section-card cash-settlement-panel" open={open||Boolean(pending)} onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>예수금 차이 정산 <span className="history-muted">가끔 한 번, 모아서 확인</span></summary>
    <p>증권사 잔고와 남은 차이만 정산합니다. 국내는 D+2, 해외는 결제 예정 거래가 반영된 잔고끼리 비교해주세요.</p>
    {reviewSource && <p role="status">CMA 잔고 확인에서 이어왔습니다. 이체를 이미 했다면 누락 이체를 먼저 확인하고, 정정할 현재 잔고는 MTS에서 다시 확인해주세요.</p>}
    <fieldset disabled={busy||disabled||Boolean(pending)} className="settlement-fields">
      <label>계좌<select className="input-select" value={aid} onChange={e=>edit(setAid,e.target.value)}><option value="">계좌 선택</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
      <label>통화<select className="input-select" value={currency} onChange={e=>edit(setCurrency,e.target.value)}><option>KRW</option><option>USD</option></select></label>
      {context&&<p>앱 예수금 <strong>{format(context.cash[key])}</strong></p>}
      <label>증권사에서 확인한 실제 잔고<input className="input-number" type="number" min="0" step={currency==='USD'?'.01':'1'} value={balance} onChange={e=>edit(setBalance,e.target.value)}/></label>
      <label>차이 구분<select className="input-select" value={classification} onChange={e=>edit(setClassification,e.target.value)}><option value="BALANCE_SETTLEMENT">잔고 차이 · 원인 미확인 / 반올림</option><option value="COST_SETTLEMENT">실제 거래비용 차이로 확인함</option></select></label>
      {currency==='USD'&&context&&!Number(context.state?.usd_balance)&&Number(balance)>0&&<label>확인한 달러 평균 취득환율<input className="input-number" type="number" min="0" step="any" value={rate} onChange={e=>edit(setRate,e.target.value)}/></label>}
      <label>메모 · 선택<input className="input-text" value={reason} maxLength="2000" onChange={e=>edit(setReason,e.target.value)} placeholder="월말 잔고 확인 등"/></label>
      {reviewSource && <label><input type="checkbox" checked={reviewedBalance} onChange={e=>setReviewedBalance(e.target.checked)}/>입출금·이체 누락을 확인했고, 입력한 금액이 MTS의 현재 잔고와 같습니다.</label>}
      <button type="button" className="btn btn-secondary" disabled={(reviewSource&&!reviewedBalance)||!context||balance===''} onClick={check}>차이 확인</button>
    </fieldset>
    {shown&&<div className="settlement-preview"><strong>{accounts.find(a=>a.id===shown.account_id)?.account_alias} · {format(shown.balance)}로 맞추기</strong>
      {preview&&<p>앱 {format(preview.before.cash[shown.currency==='USD'?'deposit_usd':'deposit_krw'])} → 실제 {format(shown.balance)} · 차이 {format(preview.delta)}</p>}
      <p>{shown.kind==='COST_SETTLEMENT'?'확인한 비용 차이':'수수료로 확정하지 않은 잔고 차이'}로 감사 이력을 남깁니다. 달러 잔고 정산은 현금 원가도 함께 맞춥니다.</p>
      <button type="button" className="btn btn-primary btn-block" disabled={busy||disabled||(!pending&&reviewSource&&!reviewedBalance)} onClick={save}>{pending?'같은 요청의 저장 결과 확인':'확인한 차이 정산'}</button>
    </div>}
    {message&&<p role="status">{message}</p>}
    {completed && reviewSource && onReturnToInput && <button type="button" className="btn btn-primary" onClick={onReturnToInput}>NH 알림·이체 입력으로 돌아가기</button>}
  </details>;
}
