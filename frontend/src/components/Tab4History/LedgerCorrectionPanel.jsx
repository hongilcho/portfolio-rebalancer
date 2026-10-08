import React,{useEffect,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW,formatUSD} from '../../utils/formatters';
import {normalizeCorrection,restoreCorrection} from '../../utils/ledgerCorrection';
import {kstToday} from '../../utils/depositMaturities';
const labels={PAST_WITHDRAWAL:'과거 출금 누락',CASH:'예수금 정정·초기 잔고',HOLDING:'수량·평단가 정정·초기 보유 등록'};
const blank=()=>({kind:'PAST_WITHDRAWAL',account_id:'',event_date:kstToday(),reason:'',currency:'KRW',amount:'',balance:'',usd_average_rate:'',asset_id:'',quantity:'',avg_price:'',avg_price_usd:'',buy_fx_rate:'',first_buy_date:'',manual_dividend_override:''});
function HistoryReview({history,decisions,onChange,disabled}){
  return history.length>0 && <div className="history-record-list"><h4>과거 평가 기록 확인</h4><p className="history-muted">당시 기록에도 같은 누락·오차가 포함됐는지 확인해주세요. 모르면 미확정으로 남길 수 있습니다.</p>{history.map(h=><div key={h.key} className="history-notice-row">
    <b>{h.key==='baseline'?'성과 시작 기준':h.date} {h.key==='baseline' && h.date}</b>
    <p>기록된 수량/예수금 {h.recorded_amount ?? '근거 없음'} · 평가액 {formatKRW(h.value)}{h.can_correct && ` → 보정 시 ${formatKRW(h.corrected_value)}`}</p>
    <select className="input-select" aria-label={`${h.key} 과거 오차 확인`} disabled={disabled} value={decisions[h.key] || 'UNKNOWN'} onChange={e=>onChange(h.key,e.target.value)}>
      <option value="UNKNOWN">확인하지 못함 · 성과 미확정</option><option value="ERROR" disabled={!h.can_correct}>같은 오차 포함 · 보정</option><option value="NORMAL">이미 정상인 기록 · 유지</option>
    </select>{h.error && <small>{h.error}</small>}
  </div>)}</div>;
}
export default function LedgerCorrectionPanel({portfolioId,accounts,assets,active=true,disabled=false,onChanged,onBusyChange,reviewRequest=null}){
  const storageKey=`ledger-correction-pending/v1/${portfolioId}`;
  const [initial]=useState(()=>{try{return restoreCorrection(localStorage.getItem(storageKey));}catch{return null;}});
  const [open,setOpen]=useState(Boolean(initial));const [mode,setMode]=useState('manual');
  const [form,setForm]=useState(initial?.proposal || blank());const [pending,setPending]=useState(initial);
  const [context,setContext]=useState(null);const [preview,setPreview]=useState(null);const [decisions,setDecisions]=useState({});
  const [reviewId,setReviewId]=useState('');const [confirmed,setConfirmed]=useState(false);const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');const [message,setMessage]=useState('');const [revision,setRevision]=useState(0);
  const [entries,setEntries]=useState([]);const [comparison,setComparison]=useState(null);
  useEffect(()=>{onBusyChange?.(busy || Boolean(pending));},[busy,pending,onBusyChange]);
  useEffect(()=>{try{if(pending)localStorage.setItem(storageKey,JSON.stringify(pending));else localStorage.removeItem(storageKey);}catch{setError('정정 요청 임시 저장을 사용할 수 없습니다. 저장 결과 확인 전에는 창을 닫지 마세요.');}},[pending,storageKey]);
  useEffect(()=>{
    if(!open || !active)return;let cancelled=false;
    api.getLedgerCorrections(portfolioId).then(r=>{if(!cancelled)setEntries(r.adjustments);}).catch(e=>{if(!cancelled)setError(e.message);});
    return()=>{cancelled=true;};
  },[portfolioId,open,active,revision]);
  useEffect(()=>{
    if(!open || !active || !form.account_id)return;let cancelled=false;setContext(null);if(!reviewId)setPreview(null);setConfirmed(false);setComparison(null);
    api.getLedgerAccount(portfolioId,form.account_id).then(r=>{if(!cancelled){setContext(r);if(!pending)setForm(f=>({...f,balance:r.state.cash[f.currency==='USD'?'deposit_usd':'deposit_krw'],usd_average_rate:r.state.state?.usd_balance>0?r.state.state.cost_krw/r.state.state.usd_balance:''}));}}).catch(e=>{if(!cancelled)setError(e.message);});
    return()=>{cancelled=true;};
  },[portfolioId,open,active,form.account_id,revision,pending,reviewId]);
  const change=(key,value)=>{setForm(f=>({...f,[key]:value}));setPreview(null);setReviewId('');setConfirmed(false);setMessage('');setError('');
    if(key==='account_id')setForm(f=>({...f,amount:'',balance:'',reason:'',asset_id:'',quantity:'',avg_price:'',avg_price_usd:'',buy_fx_rate:'',first_buy_date:'',manual_dividend_override:''}));
    if(key==='currency' && context)setForm(f=>({...f,balance:context.state.cash[value==='USD'?'deposit_usd':'deposit_krw']}));
    if(key==='asset_id' && context){const h=context.state.holdings.find(h=>h.asset_id===value) || {};setForm(f=>({...f,quantity:h.quantity || 0,avg_price:h.original_avg_price || h.avg_price || 0,avg_price_usd:h.original_avg_price_usd || h.avg_price_usd || 0,buy_fx_rate:h.buy_fx_rate || 0,first_buy_date:h.first_buy_date || '',manual_dividend_override:h.manual_dividend_override ?? ''}));}
  };
  const run=async task=>{setBusy(true);setError('');try{await task();}catch(e){setError(e.message);}finally{setBusy(false);}};
  const makePreview=()=>run(async()=>{
    if(form.kind==='HOLDING' && form.quantity==='')throw new Error('실제 보유 수량을 입력해주세요.');
    if(form.kind==='CASH' && form.balance==='')throw new Error('정정할 실제 예수금을 입력해주세요.');
    const p=normalizeCorrection(form);const r=await api.previewLedgerCorrection(portfolioId,p);setPreview({...r,proposal:p});setDecisions({});setConfirmed(false);setReviewId('');
  });
  const save=()=>run(async()=>{
    const request=pending || {request_id:crypto.randomUUID(),token:preview.token,proposal:preview.proposal,decisions,confirmed:true};
    setPending(request);let recorded=false;
    try{await api.commitLedgerCorrection(portfolioId,request);recorded=true;setPending(null);setPreview(null);setForm(f=>({...f,amount:'',reason:'',asset_id:''}));setConfirmed(false);setRevision(n=>n+1);setMessage('장부 정정을 저장했습니다. 미확정 과거 기록은 아래에서 계속 확인할 수 있습니다.');await onChanged();}
    catch(e){if(recorded)throw new Error('정정은 저장됐지만 화면 갱신에 실패했습니다. 다시 등록하지 말고 새로고침해주세요.');if(e.status && e.status<500){setPending(null);setPreview(null);setConfirmed(false);setRevision(n=>n+1);}throw e;}
  });
  const checkHistory=id=>run(async()=>{const r=await api.reviewLedgerCorrection(portfolioId,id);setReviewId(id);setPreview(r);setDecisions({});setConfirmed(false);setMode('manual');});
  const saveReview=()=>run(async()=>{const req=pending || {request_id:crypto.randomUUID(),token:preview.token,decisions,confirmed:true,review_id:reviewId};setPending(req);
    let recorded=false;try{const {review_id,...body}=req;await api.confirmLedgerHistory(portfolioId,review_id,body);recorded=true;setPending(null);setPreview(null);setReviewId('');setRevision(n=>n+1);setMessage('과거 성과 기록의 확인 내용을 저장했습니다. 현재 예수금은 다시 변경하지 않습니다.');await onChanged();}
    catch(e){if(recorded)throw new Error('확인은 저장됐지만 화면 갱신에 실패했습니다. 새로고침해주세요.');if(e.status && e.status<500){setPending(null);setPreview(null);setReviewId('');}throw e;}
  });
  const undo=id=>{if(window.confirm('이 정정의 잔고·원가·과거 성과 보정을 함께 되돌릴까요? 후속 변경이 있으면 취소가 차단됩니다.'))run(async()=>{await api.undoLedgerCorrection(portfolioId,id);setRevision(n=>n+1);await onChanged();setMessage('정정을 취소했습니다.');});};
  const compare=()=>run(async()=>{setComparison(await api.compareNamuh({portfolio_id:portfolioId,account_id:form.account_id}));setMessage('조회 결과입니다. 장부는 변경하지 않았습니다.');});
  const selectBroker=(currency,value)=>{setForm(f=>({...f,kind:'CASH',currency,balance:value,reason:'나무 잔고 대조 후 실제 예수금 정정'}));setMode('manual');setPreview(null);setConfirmed(false);};
  useEffect(()=>{
    if(!reviewRequest)return;let cancelled=false;setOpen(true);setMode('manual');setReviewId(reviewRequest.id);setBusy(true);setError('');
    api.reviewLedgerCorrection(portfolioId,reviewRequest.id).then(r=>{if(!cancelled){setPreview(r);setDecisions({});setConfirmed(false);}}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setBusy(false);});
    return()=>{cancelled=true;};
  },[portfolioId,reviewRequest]);
  const asset=assets.find(a=>a.id===form.asset_id),us=asset?.market==='US';
  const locked=busy || disabled || Boolean(pending);
  const history=preview?.history || [];
  const pendingSummary=pending && <details><summary>저장 확인 중인 요청 내용</summary><p>{pending.proposal?`${pending.proposal.event_date} · ${labels[pending.proposal.kind]} · ${pending.proposal.reason}`:'과거 평가 기록 추가 확인'}</p>{pending.proposal && <p>계좌 {accounts.find(a=>a.id===pending.proposal.account_id)?.account_alias || '계좌 확인 필요'} · {pending.proposal.kind==='HOLDING'?`수량 ${pending.proposal.quantity} · 단가 ${pending.proposal.avg_price_usd || pending.proposal.avg_price}`:pending.proposal.kind==='PAST_WITHDRAWAL'?`누락 출금 ${pending.proposal.amount} ${pending.proposal.currency}`:`목표 예수금 ${pending.proposal.balance} ${pending.proposal.currency}`}</p>}{Object.entries(pending.decisions).map(([key,v])=><p key={key}>{key} · {v==='ERROR'?'동일 오차 보정':v==='NORMAL'?'정상 기록 유지':'미확정'}</p>)}</details>;
  const waiting=entries.filter(e=>!e.reversed_at && e.history.some(h=>h.decision==='UNKNOWN'));
  return <details className="section-card history-help" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>장부 확인 및 정정</summary>
    <p className="history-muted">실제 매매·기준일 이후 입출금은 위의 일반 입력을 사용하세요. 여기서는 초기 잔고·누락·오류를 사유와 함께 정정합니다.</p>
    <fieldset className="ledger-correction-form" disabled={locked} style={{border:0,padding:0}}>
      <div className="history-inline-choice"><button type="button" aria-pressed={mode==='manual'} onClick={()=>setMode('manual')}>수동 정정</button><button type="button" aria-pressed={mode==='compare'} onClick={()=>setMode('compare')}>나무 잔고 대조</button></div>
      <label>계좌<select className="input-select" aria-label="정정 계좌" value={form.account_id} onChange={e=>change('account_id',e.target.value)}><option value="">계좌 선택</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
      {form.account_id && !context && !error && <p className="history-muted" role="status">현재 장부 조회 중…</p>}
      <fieldset className="ledger-correction-fields" disabled={(!context && !reviewId) || locked}>
      {mode==='compare'?<div><p>증권사 제공 잔고와 비교합니다. 수량·평단가를 자동으로 덮어쓰지 않습니다.</p><button className="btn btn-secondary" disabled={!form.account_id} onClick={compare}>나무 잔고 조회·대조</button>{comparison && <div>
        {['KRW','USD'].map(currency=>{const key=currency==='KRW'?'krw':'usd',reported=comparison[`broker_${key}`],book=comparison[`book_${key}`],format=currency==='KRW'?formatKRW:formatUSD;return <p key={currency}>{currency} · 앱 {format(book)} / 증권사 {reported==null?'미제공':format(reported)}{reported!=null && <button className="btn btn-secondary btn-sm" onClick={()=>selectBroker(currency,reported)}>정정할 값으로 가져오기</button>}</p>;})}
        {!comparison.holdings_provided && <p>이 응답에는 종목 보유 내역이 없습니다. 수량을 0으로 처리하지 않습니다.</p>}
        {comparison.holdings.map((h,i)=><p key={i}>{h.name} · 앱 수량 {h.book_quantity} / 증권사 {h.broker_quantity} · 평단가 {h.broker_avg_price_usd || h.broker_avg_price || '미제공'}{h.asset_id && <button className="btn btn-secondary btn-sm" onClick={()=>{change('kind','HOLDING');change('asset_id',h.asset_id);setForm(f=>({...f,quantity:h.broker_quantity,reason:'나무 보유 잔고 대조 후 수량·원가 확인'}));setMode('manual');}}>수량 정정 검토</button>}{!h.asset_id && ' · 종목 마스터 등록 필요'}</p>)}
      </div>}</div>:<div>
        {!reviewId && <>
          <label>정정 종류<select className="input-select" value={form.kind} onChange={e=>change('kind',e.target.value)}>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
          <label>실제 발생일<input className="input-text" type="date" max={kstToday()} value={form.event_date} onChange={e=>change('event_date',e.target.value)}/></label>
          {form.kind!=='HOLDING'?<>
            <label>통화<select className="input-select" value={form.currency} onChange={e=>change('currency',e.target.value)}><option>KRW</option><option>USD</option></select></label>
            {context && <p>현재 예수금 {form.currency==='USD'?formatUSD(context.state.cash.deposit_usd):formatKRW(context.state.cash.deposit_krw)}</p>}
            <label>{form.kind==='PAST_WITHDRAWAL'?'누락된 출금액':'정정할 실제 예수금'}<input className="input-number" type="number" min="0" step="any" value={form.kind==='PAST_WITHDRAWAL'?form.amount:form.balance} onChange={e=>change(form.kind==='PAST_WITHDRAWAL'?'amount':'balance',e.target.value)}/></label>
            {form.currency==='USD' && <label>확인한 달러 평균 취득환율<input className="input-number" type="number" min="0" step="any" value={form.usd_average_rate} onChange={e=>change('usd_average_rate',e.target.value)}/></label>}
          </>:<>
            <label>종목<select className="input-select" value={form.asset_id} onChange={e=>change('asset_id',e.target.value)}><option value="">종목 선택</option>{assets.filter(a=>!a.is_deposit).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
            <label>실제 보유 수량<input className="input-number" type="number" min="0" step="any" value={form.quantity} onChange={e=>change('quantity',e.target.value)}/></label>
            <label>{us?'달러 매입단가':'매입단가 · 배당 차감 전'}<input className="input-number" type="number" min="0" step="any" value={us?form.avg_price_usd:form.avg_price} onChange={e=>change(us?'avg_price_usd':'avg_price',e.target.value)}/></label>
            {us && <label>확인한 매입환율<input className="input-number" type="number" min="0" step="any" value={form.buy_fx_rate} onChange={e=>change('buy_fx_rate',e.target.value)}/></label>}
            <label>배당 산정 시작일<input className="input-text" type="date" max={kstToday()} value={form.first_buy_date} onChange={e=>change('first_buy_date',e.target.value)}/></label>
            <label>배당금 수동 보정 · 공란은 자동 계산<input className="input-number" type="number" min="0" step="any" value={form.manual_dividend_override} onChange={e=>change('manual_dividend_override',e.target.value)}/></label>
            <p>초기 등록·정정은 매수로 처리하지 않으며 예수금을 차감하지 않습니다. 미국 자산의 보유 원가와 달러 현금 원가는 별도로 확인합니다.</p>
          </>}
          <label>정정 사유<textarea className="input-text" rows="2" value={form.reason} onChange={e=>change('reason',e.target.value)}/></label>
          <button className="btn btn-secondary" disabled={!context || form.reason.trim().length<3} onClick={makePreview}>변경 전후·성과 영향 미리보기</button>
        </>}
        {preview && <>{!reviewId && <p>변경량 {preview.delta} {form.kind==='HOLDING'?'수량':form.currency} · 변경 전 {form.kind==='HOLDING'?preview.before.holdings.find(h=>h.asset_id===form.asset_id)?.quantity || 0:preview.before.cash[form.currency==='USD'?'deposit_usd':'deposit_krw']} → 변경 후 {form.kind==='HOLDING'?preview.proposal.quantity:form.kind==='CASH'?preview.proposal.balance:preview.before.cash[form.currency==='USD'?'deposit_usd':'deposit_krw']+preview.delta}</p>}
          <HistoryReview history={history} decisions={decisions} disabled={locked} onChange={(key,value)=>{setDecisions(d=>({...d,[key]:value}));setConfirmed(false);}}/>
        </>}
      </div>}
      </fieldset>
    </fieldset>
    {(preview || pending) && mode==='manual' && <div className="history-confirm-footer"><label><input type="checkbox" disabled={busy || disabled} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>변경 전후 값·사유·과거 평가 기록 확인 내용을 검토했습니다.</label><button className="btn btn-primary" disabled={!confirmed || busy || disabled} onClick={(reviewId || pending?.review_id)?saveReview:save}>{pending?'동일 요청의 저장 결과 다시 확인':reviewId?'과거 기록 확인 내용 저장':'확인한 정정 반영'}</button></div>}
    {pendingSummary}
    {pending && <p role="alert">저장 결과가 확정될 때까지 입력을 고정합니다. 동일 요청으로 재확인하면 중복 반영하지 않습니다.</p>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {waiting.map(a=><p key={a.id}>{a.event_date} · {labels[a.kind]} · 과거 성과 미확정 <button className="btn btn-secondary btn-sm" disabled={locked} onClick={()=>checkHistory(a.id)}>남은 기록 확인</button></p>)}
    <details><summary>최근 정정·취소</summary>{entries.slice(0,5).map(a=><p key={a.id}>{a.event_date} · {labels[a.kind]} · {a.reason} {a.reversed_at?'취소됨':<button className="btn btn-secondary btn-sm" disabled={locked} onClick={()=>undo(a.id)}>정정 취소</button>}</p>)}<p>이전 정정은 기록 조회에서 확인합니다.</p></details>
  </details>;
}
