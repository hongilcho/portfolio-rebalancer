import React,{useState,useEffect,useRef} from 'react';
import {api} from '../../utils/api';

export default function PlanSave({portfolioId,result,onStartInvestment,onSaved}) {
  const [name,setName]=useState('리밸런싱 계획'),[saved,setSaved]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const saving=useRef(false);
  useEffect(()=>{setSaved(null);setError('');},[result]);
  if(!result?.success || !result.trade_plan?.length)return null;
  const save=async()=>{
    if(saving.current || saved || !name.trim())return;
    saving.current=true;setBusy(true);setError('');
    try {
      const response=await api.savePlan(portfolioId,{...result.inputs,name:name.trim(),trade_plan:result.trade_plan,transfer_plan:result.transfer_plan || []});
      setSaved({id:response.id,name:name.trim()});onSaved?.();
    } catch(e){setError(e.message);} finally{setBusy(false);saving.current=false;}
  };
  const buyOnly=result.trade_plan.every(line=>line.type==='BUY');
  return <section className="section-card plan-save" aria-label="계획 저장">
    <div className="section-title"><span>계산 결과를 투자 계획으로 저장</span></div>
    <p className="history-muted">매매 수량과 이체 지시를 확인한 뒤 이름을 붙여 저장하세요.</p>
    {saved?<div className="plan-save-complete" role="status">
      <p><strong>{saved.name}</strong> 계획을 저장했습니다.</p>
      {onStartInvestment && buyOnly?<button type="button" className="btn btn-primary btn-block" onClick={()=>onStartInvestment({plan_id:saved.id})}>이 계획으로 투자 실행 준비</button>:!buyOnly && <p>매도 포함 계획은 현재 8번 투자 실행을 지원하지 않습니다. 실제 거래는 5번에서 기록할 수 있습니다.</p>}
    </div>:<>
      <label className="form-label">계획 이름<input className="input-text" aria-label="계획 이름" maxLength={120} value={name} disabled={busy} onChange={e=>setName(e.target.value)} /></label>
      <button type="button" className="btn btn-primary btn-block" disabled={busy || !name.trim()} onClick={save}>{busy?'계획 저장 중…':'현재 계산 결과를 계획으로 저장'}</button>
    </>}
    {error && <p role="alert">{error}</p>}
    <small className="history-muted">계획 저장은 장부와 예수금을 변경하지 않습니다.</small>
  </section>;
}
