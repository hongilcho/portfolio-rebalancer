import React,{useEffect,useRef,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW,formatUSD} from '../../utils/formatters';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,singleSubmission} from '../../utils/bookkeepingRequest';
export default function CashReturnPlanner({portfolioId,cycle,onOpen,onBusyChange,canStart=true,disabled=false}){
 const key='cash-return-plan/v1/'+portfolioId+'/'+cycle.id,lock=useRef(false);
 const [pending,setPending]=useState(()=>readPendingRequest(key));
 const initialPending=useRef(pending),representative=cycle.payload?.representative_account_id;
 const [open,setOpen]=useState(Boolean(pending)),[data,setData]=useState(null),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState(''),[preview,setPreview]=useState(null),[saved,setSaved]=useState(null);
 const [form,setForm]=useState(()=>pending?.payload || {request_id:crypto.randomUUID(),name:(cycle.name+' · CMA 회수').slice(0,120),destination_account_id:'',keep_amounts:{}});
 useEffect(()=>{if(!open)return;let cancelled=false;setLoading(true);api.getCashReturnOptions(portfolioId,cycle.id).then(result=>{if(cancelled)return;setData(result);if(!initialPending.current)setForm(old=>{const destination=result.cma_accounts.find(a=>a.id===representative) || result.cma_accounts[0];return {...old,destination_account_id:String(destination?.id || ''),keep_amounts:Object.fromEntries(result.accounts.filter(a=>a.transfer_allowed && Number(a.deposit_krw)>0 && a.id!==destination?.id).map(a=>[a.id,0]))};});}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[open,portfolioId,cycle.id,representative]);
 useEffect(()=>()=>onBusyChange?.(false),[onBusyChange]);
 const edit=patch=>{setForm(old=>({...old,...patch,request_id:crypto.randomUUID()}));setPreview(null);setError('');};
 const action=fn=>singleSubmission(lock,async()=>{setBusy(true);onBusyChange?.(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);onBusyChange?.(false);}});
 const save=()=>action(async()=>{const row=pending || {payload:{...form,preview_token:preview.preview_token}};if(!pending){persistPendingRequest(key,row);setPending(row);}try{const result=await api.saveCashReturn(portfolioId,cycle.id,row.payload);clearPendingRequest(key);setPending(null);setSaved(result);}catch(e){if(e.status && e.status<500 && ![401,403,429].includes(e.status)){clearPendingRequest(key);setPending(null);setPreview(null);}throw e;}});
 const selected=Object.keys(form.keep_amounts),total=preview?.total_krw;
 return <section className="section-card cash-return-planner" aria-label="CMA 현금 회수 계획"><h3>남은 현금 CMA로 모으기</h3>
 {!open?<button className="btn btn-secondary btn-block" disabled={disabled} onClick={()=>setOpen(true)}>남은 현금 CMA 회수 계획 만들기</button>:<>
 {error && <p role="alert">{error}</p>}{loading && <p>현재 예수금 확인 중…</p>}
 {saved?<><p>현금 회수 계획을 저장했습니다. 실제 이체를 진행하고 내역을 기록하세요.</p><button className="btn btn-primary btn-block" disabled={disabled || !canStart} onClick={()=>action(()=>onOpen({plan_id:saved.id}))}>이 회수 계획으로 진행</button>{!canStart && <p>진행 중인 다른 투자를 먼저 종료한 뒤 회수 계획을 시작해주세요.</p>}</>:pending?<button className="btn btn-primary" disabled={busy || disabled} onClick={save}>같은 회수 계획 저장 결과 확인</button>:data && <>
 <p className="history-muted">이번 투자에 사용된 계좌의 현재 장부 잔액입니다. 기존 현금도 포함되므로 회수할 계좌와 남길 금액을 확인하세요. 달러는 환전하지 않고 유지합니다.</p>
 <fieldset className="workflow-form" disabled={busy || disabled}>
 <label>회수 계획 이름<input aria-label="회수 계획 이름" className="input-text" maxLength={120} value={form.name} onChange={e=>edit({name:e.target.value})}/></label>
 <label>회수할 CMA 계좌<select aria-label="회수 CMA 계좌" className="input-select" value={form.destination_account_id} onChange={e=>{const keep={...form.keep_amounts};delete keep[e.target.value];edit({destination_account_id:e.target.value,keep_amounts:keep});}}><option value="">CMA 선택</option>{data.cma_accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label></fieldset>
 {!data.cma_accounts.length && <p role="alert">이 포트폴리오에서 CMA 계좌를 찾지 못했습니다. 계좌 종류 또는 별칭에 CMA가 표시된 계좌가 필요합니다.</p>}
 {data.accounts.filter(a=>a.id!==form.destination_account_id).map(a=><div className="trade-row-card" key={a.id}><strong>{a.account_alias}</strong><p>원화 {formatKRW(a.deposit_krw)} · 달러 {formatUSD(a.deposit_usd)}</p>
 {!a.transfer_allowed?<p>절세계좌 · 출금 제외, 다음 투자에 사용</p>:Number(a.deposit_krw)<=0?<p>회수할 원화 없음</p>:<>
 <label><input type="checkbox" aria-label={a.account_alias+' 회수 선택'} disabled={busy || disabled} checked={selected.includes(a.id)} onChange={e=>{const keep={...form.keep_amounts};if(e.target.checked)keep[a.id]=0;else delete keep[a.id];edit({keep_amounts:keep});}}/>원화를 CMA로 회수</label>
 {selected.includes(a.id) && <label className="execution-source">계좌에 남길 원화<input aria-label={a.account_alias+' 남길 원화'} className="input-number" type="number" min="0" max={a.deposit_krw} step="1" disabled={busy || disabled} value={form.keep_amounts[a.id]} onChange={e=>edit({keep_amounts:{...form.keep_amounts,[a.id]:Number(e.target.value)}})}/></label>}</>}</div>)}
 <button className="btn btn-secondary" disabled={busy || disabled || !form.destination_account_id || !selected.length || !form.name.trim()} onClick={()=>action(async()=>setPreview(await api.prepareCashReturn(portfolioId,cycle.id,form)))}>회수 금액 미리 확인</button>
 {preview && <div className="execution-start-review"><h4>총 회수액 {formatKRW(total)}</h4>{preview.plan.return_plan.map(row=><p key={row.account_id}>{row.account_alias} → {preview.plan.destination_alias} · {formatKRW(row.amount_krw)} / 남김 {formatKRW(row.keep_krw)}</p>)}<p className="history-muted">계획 저장은 예수금을 변경하지 않습니다.</p><button className="btn btn-primary btn-block" disabled={busy || disabled} onClick={save}>확인한 회수 계획 저장</button></div>}
 {data.plans.length>0 && <details className="execution-help"><summary>이 투자에서 만든 회수 계획 {data.plans.length}개</summary>{data.plans.map(p=><p key={p.id}>{p.name} <button className="btn btn-secondary btn-sm" disabled={busy || disabled || (!p.cycle_id && !canStart)} onClick={()=>action(()=>onOpen({plan_id:p.id,cycle_id:p.cycle_id}))}>{p.cycle_id?'회수 진행 보기':'회수 계획으로 진행'}</button></p>)}</details>}
 </>}</>}
 </section>;
}
