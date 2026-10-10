import React, { useState } from 'react';
import { api } from '../../utils/api';
import { formatKRW, formatQuantity } from '../../utils/formatters';
import { planProgress, planCandidates } from '../../utils/planProgress';

export default function SavedPlans({ portfolioId, result, onStartInvestment }) {
  const [data,setData] = useState({plans:[],candidates:[]});
  const [name,setName] = useState('리밸런싱 계획');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [open,setOpen] = useState(false);
  const [choices,setChoices] = useState({});
  const refresh = async () => setData(await api.getPlans(portfolioId));
  const run = async action => {
    setBusy(true);setError('');
    try {await action();await refresh();setOpen(true);} catch(e) {setError(e.message);} finally {setBusy(false);}
  };
  return <div className="section-card">
    {result?.success && result.trade_plan?.length>0 && <div>
      <label>계획 이름 <input className="input-text" aria-label="계획 이름" maxLength={120} value={name} onChange={e=>setName(e.target.value)} /></label>
      <button className="btn btn-primary" disabled={busy || !name.trim()} onClick={()=>run(()=>api.savePlan(portfolioId,{...result.inputs,name:name.trim(),trade_plan:result.trade_plan,transfer_plan:result.transfer_plan || []}))}>현재 계산 결과를 계획으로 저장</button>
    </div>}
    <p>계획 저장·거래 연결은 진행 확인용입니다. 매매기록·예수금을 변경하거나 증권사 주문을 전송하지 않습니다.</p>
    <button className="btn btn-secondary" disabled={busy} onClick={()=>open ? setOpen(false) : run(async()=>{})}>{open ? '저장한 계획 접기' : '저장한 계획 조회'}</button>
    {error && <p role="alert">{error}</p>}
    {open && <div>{!data.plans.length && <p>저장한 계획이 없습니다.</p>}{data.plans.map(p=><details key={p.id} className="trade-row-card">
      <summary>{p.name} · {new Date(p.created_at).toLocaleDateString('ko-KR')} · {p.archived ? '보관됨' : '진행 중'}</summary>
      {onStartInvestment && <button className="btn btn-primary" disabled={busy || (!p.execution && (p.archived || p.payload.trade_plan.some(l=>l.type!=='BUY')))} onClick={()=>onStartInvestment({plan_id:p.id,cycle_id:p.execution?.id})}>{p.execution?'투자 실행 보기':'이 계획으로 투자 실행 준비'}</button>}
      {p.execution && <p>실행에 사용한 원본 계획입니다. 목표 변경과 기록 연결은 8번 투자 실행에서 관리합니다.</p>}
      <p>계산 시나리오 {p.payload.scenario} · 신규 현금 {formatKRW(p.payload.new_cash_krw)}. 저장 후 장부에 입력한 거래를 해당 행에 연결하세요.</p>
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
      <button className="btn btn-secondary" disabled={busy || Boolean(p.execution && p.execution.status!=='CLOSED')} onClick={()=>run(()=>api.archivePlan(portfolioId,p.id,!p.archived))}>{p.archived ? '진행 중으로 복원' : '계획 보관'}</button>
    </details>)}</div>}
  </div>;
}
