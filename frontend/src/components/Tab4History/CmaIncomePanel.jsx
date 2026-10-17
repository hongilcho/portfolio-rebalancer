import React,{useEffect,useRef,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW} from '../../utils/formatters';
import {cmaStateLabel,cmaIncomeRequest,cmaInitialInterestRequest,cmaCheckAlerts} from '../../utils/cmaIncome';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,singleSubmission} from '../../utils/bookkeepingRequest';
import {draftStorage} from '../../utils/tradeDraft';

export default function CmaIncomePanel({portfolioId,active=true,disabled=false,onChanged,onBusyChange}) {
  const storage=draftStorage(''),key=`cma-income-pending/${portfolioId}`;
  const [pending,setPending]=useState(()=>readPendingRequest(key,storage)?.payload || null);
  const [data,setData]=useState(null),[aid,setAid]=useState(''),[observation,setObservation]=useState(null);
  const [preview,setPreview]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [automatic,setAutomatic]=useState(false),[daily,setDaily]=useState(false),[limit,setLimit]=useState('0');
  const [initialConfirmed,setInitialConfirmed]=useState(false),[initialReason,setInitialReason]=useState('');
  const lock=useRef(false);
  const canWrite=data?.writes_enabled===true,autoReady=data?.automatic_ready===true;
  const alerts=cmaCheckAlerts(data);
  useEffect(()=>{onBusyChange?.(busy||Boolean(pending));},[busy,pending,onBusyChange]);
  useEffect(()=>()=>onBusyChange?.(false),[onBusyChange]);
  useEffect(()=>{
    let cancelled=false;
    if(active)api.getCmaIncome(portfolioId).then(value=>{if(!cancelled)setData(value);}).catch(e=>{if(!cancelled)setError(e.message);});
    return ()=>{cancelled=true;};
  },[portfolioId,active]);
  const refresh=async()=>setData(await api.getCmaIncome(portfolioId));
  const perform=action=>singleSubmission(lock,async()=>{setBusy(true);setError('');setNotice('');
    try{await action();}catch(e){setError(e.message);}finally{setBusy(false);}});
  const select=next=>{
    setAid(next);setObservation(null);setPreview(null);setConfirmed(false);setInitialConfirmed(false);setInitialReason('');
    const account=data?.accounts.find(a=>a.id===next);
    setAutomatic(Boolean(account?.auto_apply)&&canWrite&&autoReady);setDaily(Boolean(account?.enabled));setLimit(String(account?.max_auto_interest||0));
  };
  const check=()=>perform(async()=>{
    setObservation(null);setPreview(null);setConfirmed(false);setInitialConfirmed(false);
    const obs=await api.observeCma(portfolioId,aid);setObservation(obs);
    if(obs.state==='CASH_RETURNED')setPreview(await api.previewCmaIncome(portfolioId,aid,obs.id));
  });
  const apply=(initial=false)=>perform(async()=>{
    const request=pending || (initial?cmaInitialInterestRequest(aid,preview,initialConfirmed,initialReason,crypto.randomUUID()):cmaIncomeRequest(aid,preview,confirmed,crypto.randomUUID()));
    if(!pending){persistPendingRequest(key,{payload:request},storage);setPending(request);}
    let saved=false;
    try{
      const opening=Object.hasOwn(request,'initial_interest_krw');
      const result=await (opening?api.initializeCmaInterest(portfolioId,request):api.applyCmaIncome(portfolioId,request));saved=true;
      clearPendingRequest(key,storage);setPending(null);setPreview(null);setConfirmed(false);
      setObservation(null);setInitialConfirmed(false);setInitialReason('');
      setNotice(opening?`이전 누적 이자 ${formatKRW(Number(result.initial_interest_krw))}를 별도로 정리했습니다. 지급일별 이자는 잔고를 다시 확인한 후 반영합니다.`:`CMA 이자 ${formatKRW(Number(result.interest_krw))}를 반영했습니다. 외부 입금으로 기록하지 않았습니다.`);
      await refresh();await onChanged?.();
    }catch(e){
      if(saved)throw new Error('이자는 저장됐지만 화면 갱신에 실패했습니다. 다시 입력하지 말고 새로고침해주세요.');
      if(e.status && e.status<500 && ![401,403,429].includes(e.status)){
        clearPendingRequest(key,storage);setPending(null);setPreview(null);setConfirmed(false);
      }
      throw e;
    }
  });
  return <details className="section-card history-help" open={pending||alerts.length?true:undefined}>
    <summary>CMA 잔고·이자 확인</summary>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!data?<p>기능 상태 확인 중…</p>:!data.enabled?<p>외부 연결 없는 개발을 마쳤으며 실제 조회·자동 반영은 운영 검증과 승인 후 사용할 수 있습니다.</p>:<>
      <p>NH 잔고와 지급 이자·입출금 명세를 장부와 대조합니다. 이자는 외부 투자금 입금으로 기록하지 않습니다. 초기 누적 차액은 당일 이자로 자동 처리하지 않으며, 예수금 0원·상품 전환 상태에서는 기존 장부를 유지합니다.</p>
      <p>이 포트폴리오에서 확인·반영한 CMA 이자 합계 <strong>{formatKRW(Number(data.interest_total_krw || 0))}</strong></p>
      {alerts.length>0 && <div role="alert">{alerts.map(text=><p key={text}>{text}</p>)}</div>}
      {!canWrite && <p role="status">조회 전용 상태입니다. CMA 이자 반영·취소는 서버에서 차단되어 있습니다.</p>}
      {!autoReady && <p>실제 NH 이자·입출금 명세 형식의 검증이 끝나기 전에는 자동 반영을 켤 수 없습니다.</p>}
      {pending?<div role="alert"><p>저장 결과를 확인하지 못한 요청이 있습니다. 새 요청을 만들지 않고 같은 요청으로 확인합니다. 쓰기 차단 중에는 요청을 보존하고 최근 이력을 확인합니다.</p><button disabled={busy||disabled||!canWrite} onClick={()=>apply()}>같은 이자 요청의 결과 확인</button></div>:<fieldset disabled={busy||disabled} style={{border:0,padding:0}}>
        <label>조회할 CMA 계좌<select className="input-select" aria-label="CMA 이자 계좌" value={aid} onChange={e=>select(e.target.value)}><option value="">계좌 선택</option>{data.accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
        <button type="button" className="btn btn-secondary" disabled={!aid} onClick={check}>NH CMA 잔고 확인</button>
        {observation && <p role="status">{cmaStateLabel(observation.state)} · 조회 시각 {new Date(observation.observed_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})}</p>}
        {observation?.reconciliation && <p>이자 명세 대조: {cmaStateLabel(observation.reconciliation.status)}</p>}
        {observation && <div aria-label="CMA 조회 항목">
          <p>예수금 {observation.cash_krw==null?'확인되지 않음':formatKRW(Number(observation.cash_krw))} · CMA 상품 평가액 {observation.sweep_krw==null?'확인되지 않음':formatKRW(Number(observation.sweep_krw))}</p>
          <p>예수금·CMA 상품 합계 {observation.total_krw==null?'확인되지 않음':formatKRW(Number(observation.total_krw))}</p>
          <p>출금가능금액 (참고) {observation.withdrawable_krw==null?'확인되지 않음':formatKRW(Number(observation.withdrawable_krw))}</p>
          <p>예수금이 0원이어도 출금가능금액이 표시될 수 있습니다. 출금가능금액을 계좌 총잔고나 이자 확정액으로 사용하지 않습니다. 실제 상품 잔고와 반환 상태를 확인합니다.</p>
        </div>}
        {preview && <><p>현재 장부 {formatKRW(Number(preview.book_krw))} → NH 잔고 {formatKRW(Number(preview.broker_krw))} · 잔고 차액 {formatKRW(Number(preview.interest_krw))}</p>
          {preview.can_apply===false && preview.status!=='INITIAL_BALANCE_REVIEW' && <p role="alert">{cmaStateLabel(preview.status)}. 지급 명세와 장부 대조를 마칠 때까지 이자를 반영하지 않습니다.</p>}
          {preview.can_apply===false && preview.status==='INITIAL_BALANCE_REVIEW' && <><p role="alert">{preview.source_start && preview.source_start!==preview.event_date?'조회 기간 지급 이자':'오늘 지급 이자'} {formatKRW(Number(preview.paid_interest_krw))} · 이전 차액 {formatKRW(Number(preview.prior_difference_krw))}. 초기 누적분을 오늘 이자로 합쳐 반영하지 않습니다.</p>
            {canWrite && autoReady && Number(preview.prior_difference_krw)>0 && <details><summary>이전 누적 이자 초기 정리</summary>
              <p>이전 차액만 누적 이자로 기록합니다. 과거 지급일을 추정하지 않고 현재 장부에서 인식하며, 조회 기간의 지급 이자는 별도로 남겨둡니다.</p>
              <label><input type="checkbox" checked={initialConfirmed} onChange={e=>setInitialConfirmed(e.target.checked)}/>입출금은 모두 기록했고 이전 차액은 누적 이자임을 확인했습니다.</label>
              <label>초기 정리 사유<input className="input-text" value={initialReason} maxLength={1000} onChange={e=>setInitialReason(e.target.value)}/></label>
              <button type="button" disabled={!initialConfirmed||initialReason.trim().length<10} onClick={()=>apply(true)}>이전 누적 이자만 정리</button>
            </details>}</>}
          {preview.paid_items?.length>0 && <p>은행 지급일별 이자: {preview.paid_items.map(i=>`${i.event_date} ${formatKRW(Number(i.amount_krw))}`).join(' · ')}</p>}
          {canWrite && preview.can_apply!==false && <><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>이미 발생한 입출금·이체·매매는 장부에 반영했고, 남은 차액은 CMA 이자입니다.</label>
          <button type="button" className="btn btn-primary" disabled={!confirmed || Number(preview.interest_krw)<=0} onClick={()=>apply()}>CMA 이자로 반영</button></>}</>}
        {aid && <details><summary>매일 확인 설정</summary><p>한국 시간 09:00·12:00·15:40에 하루 최대 3회 확인합니다. 반환 시각을 추정하지 않으며, 자동 반영은 동일한 현금 잔고 두 번 확인과 은행 이자·입출금 명세 대조가 모두 완료된 경우에만 진행합니다. 누락된 지급일은 마지막 반영일부터 최대 30일 범위에서 지급일별로 대조하며, 상한은 각 지급일에 적용합니다.</p>
          <label><input type="checkbox" checked={daily} onChange={e=>setDaily(e.target.checked)}/>매일 CMA 잔고 확인</label>
          <label><input type="checkbox" disabled={!canWrite||!autoReady} checked={automatic} onChange={e=>setAutomatic(e.target.checked)}/>이자 자동 반영 · 검증된 은행 명세와 장부를 대조합니다.</label>
          <label>1일 자동 반영 상한 (원)<input type="number" className="input-number" min="0" max="1000000000" value={limit} onChange={e=>setLimit(e.target.value)}/></label>
          <button type="button" className="btn btn-secondary" onClick={()=>perform(async()=>{const auto=canWrite&&autoReady&&automatic;await api.configureCma(portfolioId,aid,{enabled:daily,auto_apply:auto,max_auto_interest:limit,movements_confirmed:auto});await refresh();setNotice('매일 확인 설정을 저장했습니다.');})}>설정 저장</button>
        </details>}
      </fieldset>}
      <p>날짜별 지급 이자는 은행 명세의 지급일과 금액으로 확인합니다. 과거 누적분의 날짜나 금리·세금을 추정하지 않습니다. 기간 성과는 다음 종가 기록부터 반영되며 과거 기준점과 종가는 자동으로 바꾸지 않습니다.</p>
      <details><summary>최근 이자 반영 이력</summary>{data.income.map(r=><p key={r.id}>{r.event_date} · {formatKRW(Number(r.amount_krw))} {r.reversed_at?'취소됨':<button disabled={busy||disabled||Boolean(pending)||!canWrite} onClick={()=>perform(async()=>{await api.undoCmaIncome(portfolioId,r.account_id,r.id);await refresh();await onChanged?.();})}>이자 기록 취소</button>}</p>)}</details>
      {data.openings?.length>0 && <details><summary>초기 누적 이자 정리 이력</summary>{data.openings.map(r=><p key={r.id}>인식일 {r.recognized_on} · 이전 누적 이자 {formatKRW(Number(r.amount_krw))} · 과거 지급일 미지정 · {r.reason} {r.reversed_at?'취소됨':<button disabled={busy||disabled||Boolean(pending)||!canWrite} onClick={()=>perform(async()=>{await api.undoInitialCmaInterest(portfolioId,r.account_id,r.id);await refresh();await onChanged?.();})}>초기 이자 정리 취소</button>}</p>)}</details>}
      <details><summary>최근 매일 확인 상태</summary>{data.checks.map((r,i)=><p key={i}>{r.event_date} · {r.account_alias} · {cmaStateLabel(r.state)}</p>)}</details>
    </>}
  </details>;
}
