import {executionNotices,executionRows} from '../../utils/investmentInput';
import React, { useEffect, useState, useRef } from 'react';
import { api } from '../../utils/api';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,requireBookkeepingProtocol,singleSubmission} from '../../utils/bookkeepingRequest';
import { formatKRW } from '../../utils/formatters';
import { kstToday } from '../../utils/depositMaturities';

export default function ExternalCashFlowPanel({ portfolioId, accounts, performance, onOpenAnalysis, onCashChanged,onBusyChange,focused=false,disabled=false,executionContext=null,executionConfirmed=false }) {
  const { data, busy, error, notice, run, capture } = performance;
  const pendingKey=`manual-funds/v1/${portfolioId}`;
  const submitLock=useRef(false);
  const [pending,setPending]=useState(()=>readPendingRequest(pendingKey));
  useEffect(()=>{onBusyChange?.(busy || Boolean(pending),busy);},[busy,pending,onBusyChange]);
  const [applyCash,setApplyCash]=useState(true);
  const [flowChecked, setFlowChecked] = useState(false);
  useEffect(() => { setFlowChecked(false); }, [data]);
  const [form, setForm] = useState(() => ({ request_id: crypto.randomUUID(), account_id: '', event_date: kstToday(), direction: 'DEPOSIT', currency: 'KRW', native_amount: '', exchange_rate: 1400, notes: '' }));
  const change = (key, value) => { setForm(f => ({ ...f, [key]: value })); setFlowChecked(false); };
  const submit = async e => {
    e?.preventDefault();
    return singleSubmission(submitLock,async()=>{

      await run(async () => {
        let row=pending;
        if(!row){
          if(form.currency==='KRW' && applyCash){
            const context=await api.getNhNoticeContext(portfolioId,form.event_date);
            const account=context.accounts.find(a=>String(a.id)===form.account_id);
            if(!account)throw new Error('계좌를 다시 선택해주세요.');
            row={kind:'CASH',payload:{request_id:form.request_id,confirmed:true,
              expected_cash:{[form.account_id]:{deposit_krw:Number(account.deposit_krw),deposit_usd:Number(account.deposit_usd)}},
              rows:[{kind:form.direction,account_id:form.account_id,event_date:form.event_date,krw_amount:Number(form.native_amount),notes:form.notes}]}};
          }else if(form.currency==='USD' && applyCash){
            await requireBookkeepingProtocol(api);
            row={kind:'USD',account_id:form.account_id,payload:{request_id:form.request_id,portfolio_id:portfolioId,
              kind:form.direction,occurred_at:`${form.event_date}T12:00:00+09:00`,usd_amount:Number(form.native_amount),
              krw_amount:0,rate:Number(form.exchange_rate),notes:form.notes,flow_mode:'EXTERNAL',existing_flow_id:null}};
          }else row={kind:'FLOW',payload:{...form,native_amount:Number(form.native_amount),exchange_rate:form.currency==='KRW'?1:Number(form.exchange_rate)}};
          if(executionContext){
            if(row.kind==='CASH')row.payload.rows=executionNotices(row.payload.rows,executionContext,executionConfirmed);
            else if(row.kind==='USD'){const [linked]=executionRows([{...row.payload,account_id:row.account_id,currency:'USD'}],executionContext,executionConfirmed);row.payload.execution=linked.execution;}
            else throw new Error('이력만 저장하는 입출금은 투자 자금 준비로 연결하지 않습니다. 잔고 반영을 선택하거나 5번에서 연결 없이 기록해주세요.');
          }
          persistPendingRequest(pendingKey,row);setPending(row);
        }
        let recorded=false;
        try{
          if(row.kind==='CASH')await api.commitNhNotices(portfolioId,row.payload);
          else if(row.kind==='USD')await api.recordUsdEvent(row.account_id,row.payload);
          else await api.addPerformanceFlow(portfolioId,row.payload);
          recorded=true;clearPendingRequest(pendingKey);setPending(null);
          setForm(f=>({...f,request_id:crypto.randomUUID(),native_amount:'',notes:''}));setFlowChecked(false);
          await onCashChanged?.();await capture();
        }catch(error){
          if(recorded)throw new Error('입출금은 저장됐지만 화면 갱신에 실패했습니다. 다시 입력하지 말고 새로고침해주세요.');
          if(error.status && error.status<500 && ![401,403,429].includes(error.status)){clearPendingRequest(pendingKey);setPending(null);setFlowChecked(false);setForm(f=>({...f,request_id:crypto.randomUUID()}));}
          throw error;
        }
    });

    });
  };

  const recordedFlows=data?.flows || [];
  const nativeAmount = Number(form.native_amount);
  const validFlow = (Boolean(data?.tracking) || applyCash) && accounts.some(a => String(a.id) === form.account_id) && flowChecked && Number.isFinite(nativeAmount) && nativeAmount > 0
    && (form.currency === 'KRW' || (Number.isFinite(Number(form.exchange_rate)) && Number(form.exchange_rate) > 0));
  return <section className={`section-card workflow-panel ${focused?'history-focused':''}`}>{focused && <div className="history-section-heading"><h3>외부 투자자금 입출금</h3></div>}<details open={focused || undefined}>
    <summary className={focused?'history-hidden-summary':''} style={{ cursor: 'pointer', fontWeight: 700 }}>🏦 외부 투자자금 입출금 기록</summary>
    {error && <p role="alert">입출금 기록: {error}</p>}{notice && <p>{notice}</p>}
        {pending && <div role="alert"><p>입출금 저장 결과를 같은 요청으로 확인합니다.</p><button type="button" className="btn btn-primary" disabled={busy || disabled} onClick={submit}>같은 요청의 결과 다시 확인</button></div>}
    {!data ? <p>입출금 기록을 조회 중입니다.</p> : <div>
        {!data.tracking && <p>아직 성과 시작 기준이 없습니다. 실제 입출금은 예수금·원가에 먼저 반영할 수 있습니다. 입력 후 7번 ‘분석 및 확인’에서 성과 시작 기준을 등록해주세요.</p>}
        <details className="history-help"><summary>입출금 구분·예수금 반영 안내</summary><p>급여·생활비 계좌 등 이 포트폴리오 밖에서 들어온 투자금과 밖으로 인출한 금액만 기록하세요. 같은 포트폴리오 안의 계좌 이동·매수/매도·환전·배당은 제외합니다. 포트폴리오 간 이동은 양쪽에 각각 기록합니다.</p>
        <p>원화 입출금은 예수금에도 함께 반영할 수 있습니다. 이미 잔고 수정·동기화로 반영했다면 기록만 저장하세요. 달러 외부 입출금도 예수금·원가·성과 기록을 함께 저장합니다. 배당·이자 입금은 달러 관리에서 구분하여 등록하세요.</p></details>
        <form onSubmit={submit}>
          <fieldset disabled={busy || disabled || Boolean(pending)} className="workflow-form">
            <label>입출금 날짜 <input aria-label="입출금 날짜" className="input-text" type="date" min={data.tracking?.baseline_date} max={kstToday()} required value={form.event_date} onChange={e=>change('event_date',e.target.value)} /></label>
            <label>입출금 계좌 <select aria-label="입출금 계좌" className="input-select" required value={form.account_id} onChange={e=>change('account_id',e.target.value)}><option value="">계좌 선택</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
            <label>방향 <select aria-label="입출금 방향" className="input-select" value={form.direction} onChange={e=>change('direction',e.target.value)}><option value="DEPOSIT">외부에서 입금</option><option value="WITHDRAW">외부로 출금</option></select></label>
            <label>통화 <select aria-label="입출금 통화" className="input-select" value={form.currency} onChange={e=>change('currency',e.target.value)}><option value="KRW">원화</option><option value="USD">달러</option></select></label>
            <label>입출금 금액 <input aria-label="입출금 금액" className="input-number" type="number" min="0.00000001" step="any" required value={form.native_amount} onChange={e=>change('native_amount',e.target.value)} /></label>
            {form.currency==='USD' && <label>입출금 당시 평가환율 <input aria-label="입출금 당시 평가환율" className="input-number" type="number" min="0.01" step="any" required value={form.exchange_rate} onChange={e=>change('exchange_rate',e.target.value)} /></label>}
            {<label>예수금 반영 <select className="input-select" value={applyCash?'APPLY':'REFLECTED'} onChange={e=>{setApplyCash(e.target.value==='APPLY');setFlowChecked(false);}}><option value="APPLY">예수금에도 입출금 반영</option><option value="REFLECTED" disabled={!data.tracking}>잔고에 이미 반영됨 · 기록만 저장</option></select></label>}
            <label>메모 <input aria-label="입출금 메모" className="input-text" maxLength={2000} value={form.notes} onChange={e=>change('notes',e.target.value)} /></label>
            <p>기록할 원화 환산액: {formatKRW(nativeAmount*(form.currency==='USD' ? Number(form.exchange_rate) : 1))}</p>
            <label className="workflow-wide"><input type="checkbox" checked={flowChecked} onChange={e=>setFlowChecked(e.target.checked)} />외부 입출금이며, 선택한 예수금 반영 방식과 기존 기록 중복 여부를 확인했습니다.</label>
            <button className="btn btn-primary" type="submit" disabled={!validFlow}>외부 입출금 기록 저장</button>
          </fieldset>
        </form>
        {!focused && <details><summary>입출금 기록 확인 · {recordedFlows.filter(f=>!f.voided).length}건</summary>{recordedFlows.map(f=><p key={f.id}>{f.event_date} · {accounts.find(a=>a.id===f.account_id)?.account_alias || '삭제된 계좌'} · {f.amount_krw>0 ? '입금' : '출금'} {formatKRW(Math.abs(f.amount_krw))} · {f.native_amount} {f.currency} · {f.notes} {f.voided && '(취소됨)'} <button className="btn btn-secondary btn-sm" disabled={busy || disabled} onClick={()=>run(()=>api.voidPerformanceFlow(portfolioId,f.id,!f.voided))}>{f.voided ? '기록 복원' : '기록 취소'}</button></p>)}</details>}
        <details className="history-help"><summary>기록 취소·복원 안내</summary><p>성과 기록만 저장한 입출금의 취소·복원은 예수금을 변경하지 않습니다. 예수금과 함께 반영한 입출금은 NH 알림 가져오기의 반영 이력에서 묶음 취소하세요. 예금 장부 등록 자체는 실제 자금 이동을 뜻하지 않습니다. 포트폴리오 밖에서 실제 투자금이 들어오거나 나간 경우에만 외부 입출금으로 기록하세요.</p></details>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenAnalysis}>7. 분석 및 확인에서 기간 성과 확인</button>
    </div>}
  </details></section>;
}
