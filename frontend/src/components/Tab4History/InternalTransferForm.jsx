import React,{useRef,useState,useEffect} from 'react';
import {api} from '../../utils/api';
import {kstToday} from '../../utils/depositMaturities';
import {executionNotices,canTransferOut} from '../../utils/investmentInput';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,singleSubmission} from '../../utils/bookkeepingRequest';
export default function InternalTransferForm({portfolioId,accounts,onChanged,onBusyChange,disabled,executionContext,executionConfirmed}) {
  const key='manual-transfer/v1/'+portfolioId,lock=useRef(false);
  const [pending,setPending]=useState(()=>readPendingRequest(key));
  const [form,setForm]=useState({source:'',destination:'',amount:'',date:kstToday()});
  const [busy,setBusy]=useState(false),[checked,setChecked]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{onBusyChange?.(busy || Boolean(pending),busy);},[busy,pending,onBusyChange]);
  const edit=(field,value)=>{setForm(old=>({...old,[field]:value}));setChecked(false);};
  const submit=event=>{
    event.preventDefault();
    singleSubmission(lock,async()=>{
      setBusy(true);setMessage('');let recorded=false;
      try {
        let row=pending;
        if(!row){
          const context=await api.getNhNoticeContext(portfolioId,form.date);
          const ids=[form.source,form.destination];
          const expected=Object.fromEntries(ids.map(id=>{const account=context.accounts.find(a=>String(a.id)===id);if(!account)throw new Error('이체 계좌를 다시 확인해주세요.');return [id,{deposit_krw:Number(account.deposit_krw),deposit_usd:Number(account.deposit_usd)}];}));
          const rows=executionNotices([{kind:'WITHDRAW',account_id:form.source,destination_account_id:form.destination,external:false,event_date:form.date,krw_amount:Number(form.amount),notes:'직접 입력 · 계좌 이체'}],executionContext,executionConfirmed);
          row={payload:{request_id:crypto.randomUUID(),confirmed:true,expected_cash:expected,rows}};
          persistPendingRequest(key,row);setPending(row);
        }
        await api.commitNhNotices(portfolioId,row.payload);recorded=true;
        clearPendingRequest(key);setPending(null);setForm(old=>({...old,amount:''}));setChecked(false);
        await onChanged();setMessage('양쪽 예수금에 이체를 기록했습니다.');
      } catch(error) {
        if(!recorded && error.status && error.status<500 && ![401,403,429].includes(error.status)){clearPendingRequest(key);setPending(null);}
        setMessage(recorded?'이체는 저장됐지만 화면 갱신에 실패했습니다. 다시 입력하지 말고 새로고침해주세요.':error.message);
      }finally{setBusy(false);}
    });
  };
  return <section className="section-card history-focused"><h3>원화 계좌 이체 직접 입력</h3><p>같은 포트폴리오 안의 두 계좌에 함께 반영합니다.</p>
    {executionContext?.step.kind==='TRANSFER' && <button type="button" className="btn btn-secondary btn-sm" disabled={busy || disabled || Boolean(pending)} onClick={()=>{setForm(old=>({...old,source:executionContext.step.account_id,destination:executionContext.step.destination_account_id}));setChecked(false);}}>이번 이체의 계좌 채우기</button>}
    {message && <p role="status">{message}</p>}
    <form onSubmit={submit}><fieldset className="workflow-form" disabled={busy || disabled || Boolean(pending)}>
      <label>출금 계좌<select aria-label="이체 출금 계좌" className="input-select" required value={form.source} onChange={e=>edit('source',e.target.value)}><option value="">선택</option>{accounts.filter(canTransferOut).map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
      <label>입금 계좌<select aria-label="이체 입금 계좌" className="input-select" required value={form.destination} onChange={e=>edit('destination',e.target.value)}><option value="">선택</option>{accounts.filter(a=>String(a.id)!==form.source).map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
      <label>실제 이체일<input aria-label="이체 날짜" className="input-text" required type="date" max={kstToday()} value={form.date} onChange={e=>edit('date',e.target.value)}/></label>
      <label>이체 금액 (원)<input aria-label="이체 금액" className="input-number" required type="number" min="1" step="1" value={form.amount} onChange={e=>edit('amount',e.target.value)}/></label>
      <label className="workflow-wide"><input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)}/>실제 이체한 계좌·금액과 기존 기록의 중복 여부를 확인했습니다.</label>
      <button type="submit" className="btn btn-primary" disabled={!checked || !form.source || !form.destination || form.source===form.destination}>확인한 이체 장부에 반영</button>
    </fieldset>{pending && <button type="submit" className="btn btn-primary" disabled={busy || disabled}>같은 이체 요청의 결과 다시 확인</button>}</form>
  </section>;
}
