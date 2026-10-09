import React,{useState,useEffect,useRef} from 'react';
import {api} from '../../utils/api';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,requireBookkeepingProtocol,singleSubmission} from '../../utils/bookkeepingRequest';
import {formatKRW} from '../../utils/formatters';
import {kstToday} from '../../utils/depositMaturities';

const blank=()=>({name:'',ticker:'',deposit_principal:'',interest_rate:'',start_date:kstToday(),
  maturity_date:'',early_termination_rate:0,tax_rate:15.4,account_no:'',target_weight:0,notes:''});
export default function DepositLedgerPanel({portfolioId,assets,onChanged,disabled=false,onBusyChange,active=true}){
  const key=`manual-deposit/v1/${portfolioId}`;
  const submitLock=useRef(false);
  const [pending,setPending]=useState(()=>readPendingRequest(key));
  const [selected,setSelected]=useState('');
  const [form,setForm]=useState(blank);
  const [reason,setReason]=useState('');
  const [confirmed,setConfirmed]=useState(false);
  const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState('');
  const [entries,setEntries]=useState([]);
  const [reload,setReload]=useState(0);
  const locked=saving || disabled || Boolean(pending);
  useEffect(()=>{onBusyChange?.(saving || Boolean(pending),saving);},[saving,pending,onBusyChange]);
  useEffect(()=>{if(!active)return;let cancelled=false;api.getDepositEntries(portfolioId).then(r=>{if(!cancelled)setEntries(r.entries);}).catch(e=>{if(!cancelled)setMessage(e.message);});return()=>{cancelled=true;};},[portfolioId,reload,active]);
  const change=(field,value)=>{setForm(f=>({...f,[field]:value}));setConfirmed(false);};
  const choose=id=>{setSelected(id);setReason('');setConfirmed(false);const asset=assets.find(a=>String(a.id)===id);
    setForm(asset?Object.fromEntries(Object.keys(blank()).map(k=>[k,asset[k] ?? blank()[k]])):blank());};
  const submit=async event=>{
    event?.preventDefault();
    return singleSubmission(submitLock,async()=>{
  setMessage('');
      let row=pending;
      try{
        await requireBookkeepingProtocol(api);
        if(!row){
          const id=selected || crypto.randomUUID();
          row={payload:{request_id:crypto.randomUUID(),asset_id:id,reason,confirmed:true,asset:{...form,
            ticker:form.ticker || `DEP-${id.slice(-8).toUpperCase()}`,deposit_principal:Number(form.deposit_principal),
            interest_rate:Number(form.interest_rate),early_termination_rate:Number(form.early_termination_rate),tax_rate:Number(form.tax_rate),target_weight:Number(form.target_weight)}}};
          persistPendingRequest(key,row);setPending(row);
        }
      }catch(error){setMessage(error.message);return;}
      setSaving(true);let recorded=false;
      try{
        const result=await api.saveDepositEntry(portfolioId,row.payload);recorded=true;
        clearPendingRequest(key);setPending(null);setSelected('');setForm(blank());setReason('');setConfirmed(false);
        setReload(n=>n+1);await onChanged();setMessage(result.message);
      }catch(error){
        if(recorded)setMessage('예금 장부는 저장됐지만 화면 갱신에 실패했습니다. 다시 등록하지 말고 새로고침해주세요.');
        else {if(error.status && error.status<500 && ![401,403,429].includes(error.status)){clearPendingRequest(key);setPending(null);}setMessage(error.message);}
      }finally{setSaving(false);}
    });
  };

  const undo=async entry=>{
    if(!window.confirm('이 예금 장부의 원금·계약 조건을 이전 상태로 복원할까요?'))return;
    setSaving(true);let recorded=false;
    try{await api.undoDepositEntry(portfolioId,entry.result.asset_id,entry.request_id);recorded=true;setReload(n=>n+1);await onChanged();setMessage('예금 장부를 복원했습니다.');}
    catch(error){setMessage(recorded?'복원은 완료됐지만 화면 갱신에 실패했습니다. 새로고침해주세요.':error.message);}
    finally{setSaving(false);}
  };
  return <section className="section-card history-focused"><h3>예금 장부 · 현재 원금·계약 조건 확인</h3>
    <p className="history-muted">현재 예금 정보를 확인하여 등록·정정합니다. 계좌 예수금과 과거 성과 기록은 자동으로 변경하지 않습니다. 실제 가입·해지 자금 이동은 입출금 기록에서 구분하여 확인해주세요.</p>
    {pending && <div role="alert"><p>예금 저장 결과를 확인 중입니다.</p><button className="btn btn-primary" disabled={saving} onClick={submit}>같은 요청의 결과 다시 확인</button></div>}
    <form onSubmit={submit}><fieldset disabled={locked} className="workflow-form">
      <label>예금 선택<select className="input-select" value={selected} onChange={e=>choose(e.target.value)}><option value="">기존 예금 정보 새로 등록</option>{assets.filter(a=>a.is_deposit).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      <label>예금명<input className="input-text" required value={form.name} onChange={e=>change('name',e.target.value)}/></label>
      <label>확인한 원금<input className="input-number" type="number" required min="0" step="1" value={form.deposit_principal} onChange={e=>change('deposit_principal',e.target.value)}/></label>
      <label>연이율 (%)<input className="input-number" type="number" required min="0" max="100" step="any" value={form.interest_rate} onChange={e=>change('interest_rate',e.target.value)}/></label>
      <label>가입일<input className="input-text" type="date" required value={form.start_date} onChange={e=>change('start_date',e.target.value)}/></label>
      <label>만기일<input className="input-text" type="date" required value={form.maturity_date} onChange={e=>change('maturity_date',e.target.value)}/></label>
      <label>중도해지 이율 (%)<input className="input-number" type="number" required min="0" max="100" step="any" value={form.early_termination_rate} onChange={e=>change('early_termination_rate',e.target.value)}/></label>
      <label>세율 (%)<input className="input-number" type="number" required min="0" max="100" step="any" value={form.tax_rate} onChange={e=>change('tax_rate',e.target.value)}/></label>
      <label>예금 계좌번호<input className="input-text" value={form.account_no} onChange={e=>change('account_no',e.target.value)}/></label>
      <label>등록·정정 사유<input className="input-text" required minLength="3" value={reason} onChange={e=>{setReason(e.target.value);setConfirmed(false);}}/></label>
      <label className="workflow-wide"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>현재 예금 정보이며, 예수금·과거 성과가 자동 변경되지 않음을 확인했습니다.</label>
      <button type="submit" className="btn btn-primary" disabled={!confirmed}>확인한 예금 정보 반영</button>
    </fieldset></form>
    {message && <p role="status">{message}</p>}
    <details><summary>최근 예금 장부 기록</summary>{entries.map(entry=>{const r=entry.result;return <p key={entry.request_id}>{r.after?.name} · {formatKRW(r.after?.deposit_principal)} · {r.reason} {r.reversed?'(취소됨)':<button className="btn btn-secondary btn-sm" disabled={locked} onClick={()=>undo(entry)}>이 기록 취소</button>}</p>;})}</details>
  </section>;
}
