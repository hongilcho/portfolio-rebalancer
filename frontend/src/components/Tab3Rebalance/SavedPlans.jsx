import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../../utils/api';
import { formatKRW, formatQuantity } from '../../utils/formatters';
import { planProgress, planCandidates } from '../../utils/planProgress';

export default function SavedPlans({ portfolioId, onStartInvestment, revision=0 }) {
  const [data,setData] = useState({plans:[],candidates:[]});
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [open,setOpen] = useState(false);
  const [choices,setChoices] = useState({});
  const refresh=useCallback(async()=>setData(await api.getPlans(portfolioId)),[portfolioId]);
  const previousRevision=useRef(revision);
  const run = async action => {
    setBusy(true);setError('');
    try {await action();await refresh();setOpen(true);} catch(e) {setError(e.message);} finally {setBusy(false);}
  };
  useEffect(()=>{if(previousRevision.current===revision)return;previousRevision.current=revision;if(open)refresh().catch(e=>setError(e.message));},[revision,open,refresh]);
  return <section className="section-card saved-plans" aria-label="저장한 계획 관리">
    <div className="section-title"><span>기존 투자 계획</span></div>
    <button className="btn btn-secondary" disabled={busy} onClick={()=>open ? setOpen(false) : run(async()=>{})}>{open ? '저장한 계획 접기' : '저장한 계획 조회'}</button>
    {error && <p role="alert">{error}</p>}
    {open && <div>{!data.plans.length && <p>저장한 계획이 없습니다.</p>}{data.plans.map(p=><details key={p.id} className="trade-row-card">
      <summary>{p.name} · {new Date(p.created_at).toLocaleDateString('ko-KR')} · {p.archived ? '보관됨' : p.execution?'투자 회차 있음':'저장됨'}</summary>
      {onStartInvestment && <button className="btn btn-primary" disabled={busy || (!p.execution && (p.archived || p.payload.trade_plan.some(l=>l.type!=='BUY')))} onClick={()=>onStartInvestment({plan_id:p.id,cycle_id:p.execution?.id})}>{p.execution?'투자 실행 보기':'이 계획으로 투자 실행 준비'}</button>}
      {p.execution && <p>실행에 사용한 원본 계획입니다. 목표 변경과 기록 연결은 8번 투자 실행에서 관리합니다.</p>}
      {p.payload.plan_type==='CASH_RETURN'?<p>CMA 현금 회수 계획 · 실제 이체는 8번에서 진행·기록합니다.</p>:<p>계산 시나리오 {p.payload.scenario} · 신규 현금 {formatKRW(p.payload.new_cash_krw)}. 저장 후 장부에 입력한 거래를 해당 행에 연결하세요.</p>}
      {p.payload.trade_plan.map((l,i)=>{const progress=planProgress(p,i);const key=`${p.id}/${i}`;return <div key={key} className="trade-row-card">
        <b>{l.account_alias} · {l.asset_name} · {l.type==='BUY' ? '매수' : '매도'}</b>
        <p>계획 {formatQuantity(l.qty,'주')} ({formatKRW(l.total_krw)}) · 기록 {formatQuantity(progress.quantity,'주')} ({formatKRW(progress.amount)}) · 남음 {formatQuantity(progress.remaining,'주')}{progress.excess>0 && ` · 초과 ${formatQuantity(progress.excess,'주')}`}</p>
        {progress.links.map(t=><p key={t.trade_id}>{t.trade_date} · {formatQuantity(t.quantity,'주')} <button className="btn btn-secondary btn-sm" disabled={busy || Boolean(p.execution)} onClick={()=>run(()=>api.unlinkPlanTrade(portfolioId,p.id,t.trade_id))}>연결 해제</button></p>)}
        {!p.archived && !p.execution && <><select className="input-select" aria-label={`${p.name} ${i+1}행 실제 거래`} value={choices[key] || ''} onChange={e=>setChoices({...choices,[key]:e.target.value})}>
          <option value="">연결할 실제 거래 선택</option>{planCandidates(p,i,data.candidates).map(t=><option key={t.id} value={t.id}>{t.trade_date} · {formatQuantity(t.quantity,'주')} · {t.price} {t.currency} · {t.id.slice(-6)}</option>)}
        </select><button className="btn btn-secondary" disabled={busy || !choices[key]} onClick={()=>run(async()=>{await api.linkPlanTrade(portfolioId,p.id,{line_no:i,trade_id:choices[key]});setChoices({...choices,[key]:''});})}>선택 거래 연결</button></>}
      </div>;})}
      <p>저장 당시 이체 지시: {p.payload.transfer_plan?.length || 0}건. 이체 진행은 자동 판정하지 않습니다.</p>
      {(p.payload.transfer_plan || []).map((t,i)=><p key={i}>{t.msg}</p>)}
      {!p.execution && !p.links?.length && <button type="button" className="btn btn-secondary" disabled={busy} onClick={()=>{
        if(window.confirm(`‘${p.name}’ 계획을 삭제할까요? 삭제한 계획은 복구할 수 없습니다. 실제 장부는 변경하지 않습니다.`))run(()=>api.deletePlan(portfolioId,p.id));
      }}>계획 삭제</button>}
      {(p.execution || p.links?.length>0) && <p className="history-muted">투자 회차나 거래에 연결된 계획은 삭제하지 않고 보관합니다.</p>}
      <button className="btn btn-secondary" disabled={busy || Boolean(p.execution && p.execution.status!=='CLOSED')} onClick={()=>run(()=>api.archivePlan(portfolioId,p.id,!p.archived))}>{p.archived ? '진행 중으로 복원' : '계획 보관'}</button>
    </details>)}</div>}
  </section>;
}
