import React,{useRef,useState} from 'react';
import {api} from '../../utils/api';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,singleSubmission} from '../../utils/bookkeepingRequest';
export default function GoalEditor({portfolioId,cycle,onUpdated,onBusyChange,disabled=false}) {
  const key='investment-goals/v1/'+portfolioId+'/'+cycle.id,lock=useRef(false);
  const [pending,setPending]=useState(()=>readPendingRequest(key));
  const goals=cycle.steps.filter(s=>['BUY','DEPOSIT'].includes(s.kind));
  const [values,setValues]=useState(()=>Object.fromEntries(goals.map(s=>[s.id,{target:s.kind==='BUY'?s.target_quantity:s.target_amount,status:s.status || 'ACTIVE'}])));
  const [reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const changes=goals.filter(s=>Number(values[s.id]?.target)!==Number(s.kind==='BUY'?s.target_quantity:s.target_amount) || values[s.id]?.status!==(s.status || 'ACTIVE')).map(s=>({step_id:s.id,...values[s.id],target:Number(values[s.id].target)}));
  const save=()=>singleSubmission(lock,async()=>{
    setBusy(true);onBusyChange(true);setError('');let recorded=false;
    try{
      const row=pending || {payload:{request_id:crypto.randomUUID(),revision:cycle.revision,reason,changes}};
      if(!pending){persistPendingRequest(key,row);setPending(row);}
      await api.reviseInvestment(portfolioId,cycle.id,row.payload);recorded=true;clearPendingRequest(key);setPending(null);
      await onUpdated();
    }catch(e){if(!recorded && e.status && e.status<500 && ![401,403,429].includes(e.status)){clearPendingRequest(key);setPending(null);}setError(recorded?'목표는 저장됐습니다. 다시 변경하지 말고 새로고침해주세요.':e.message);}
    finally{setBusy(false);onBusyChange(false);}
  });
  return <details className="section-card execution-help"><summary>남은 매수 목표 변경</summary><p>완료된 기록과 원가는 유지하고 남은 이체·환전 안내를 다시 계산합니다.</p>{error && <p role="alert">{error}</p>}{pending?<button className="btn btn-primary" disabled={busy || disabled} onClick={save}>같은 목표 변경 요청 확인</button>:<>
    {goals.map(s=><div className="execution-source" key={s.id}><label>{s.title} · {s.account_alias}<input aria-label={s.title+' 목표'} type="number" className="input-number" min="0.00000001" step="any" disabled={busy || disabled} value={values[s.id]?.target || ''} onChange={e=>setValues(old=>({...old,[s.id]:{...old[s.id],target:e.target.value}}))}/></label>
      <label><input type="checkbox" disabled={busy || disabled} checked={values[s.id]?.status==='EXCLUDED'} onChange={e=>setValues(old=>({...old,[s.id]:{...old[s.id],status:e.target.checked?'EXCLUDED':'ACTIVE'}}))}/>남은 작업 제외</label></div>)}
    <label>변경 이유<input aria-label="투자 목표 변경 이유" className="input-text" maxLength={2000} value={reason} disabled={busy || disabled} onChange={e=>setReason(e.target.value)}/></label>
    <button className="btn btn-primary" disabled={busy || disabled || !changes.length || !reason.trim() || changes.some(r=>!Number.isFinite(r.target) || r.target<=0)} onClick={save}>변경한 목표 반영</button>
  </>}</details>;
}
