import React,{useCallback,useEffect,useRef,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW} from '../../utils/formatters';
import {cmaStateLabel,cmaIncomeRequest,cmaInitialInterestRequest,cmaCheckAlerts} from '../../utils/cmaIncome';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,singleSubmission} from '../../utils/bookkeepingRequest';
import {draftStorage} from '../../utils/tradeDraft';
import {cmaBalanceReview} from '../../utils/cmaBalanceReview';
import './CmaIncomePanel.css';

export default function CmaIncomePanel({portfolioId,active=true,disabled=false,onChanged,onBusyChange,onReviewBalance,onReturnToInput,revision=0}) {
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
  const account=data?.accounts?.find(a=>a.id===aid);
  const review=cmaBalanceReview(account,observation,preview);
  const money=value=>value==null?'아직 확인 전':formatKRW(value);
  useEffect(()=>{onBusyChange?.(busy||Boolean(pending));},[busy,pending,onBusyChange]);
  useEffect(()=>()=>onBusyChange?.(false),[onBusyChange]);
  useEffect(()=>{
    let cancelled=false;
    if(active)api.getCmaIncome(portfolioId).then(value=>{if(!cancelled){setData(value);setObservation(null);setPreview(null);setConfirmed(false);}}).catch(e=>{if(!cancelled)setError(e.message);});
    return ()=>{cancelled=true;};
  },[portfolioId,active,revision]);
  const refresh=async()=>setData(await api.getCmaIncome(portfolioId));
  const perform=action=>singleSubmission(lock,async()=>{setBusy(true);setError('');setNotice('');
    try{await action();}catch(e){setError(e.message);}finally{setBusy(false);}});
  const select=useCallback(next=>{
    setAid(next);setObservation(null);setPreview(null);setConfirmed(false);setInitialConfirmed(false);setInitialReason('');
    const account=data?.accounts.find(a=>a.id===next);
    setAutomatic(Boolean(account?.auto_apply)&&canWrite&&autoReady);setDaily(Boolean(account?.enabled));setLimit(String(account?.max_auto_interest||0));
  },[data,canWrite,autoReady]);
  useEffect(()=>{if(!aid && data?.accounts?.length===1)select(data.accounts[0].id);},[data,aid,select]);
  const check=()=>perform(async()=>{
    setObservation(null);setPreview(null);setConfirmed(false);setInitialConfirmed(false);
    const obs=await api.observeCma(portfolioId,aid);setObservation(obs);
    if(['CASH_RETURNED','CMA_PRINCIPAL_VERIFIED'].includes(obs.state))setPreview(await api.previewCmaIncome(portfolioId,aid,obs.id));
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
  return <details className="section-card cma-income-panel" open={pending?true:undefined}>
    <summary>CMA 잔고·이자 확인 {alerts.length>0 && <span className="cma-review-badge">확인 필요</span>}</summary>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!data?<p>잔고 확인 기능을 불러오는 중… {error && <button type="button" onClick={()=>perform(refresh)}>다시 불러오기</button>}</p>:!data.enabled?<p>외부 연결 없는 개발을 마쳤으며 실제 조회·자동 반영은 운영 검증과 승인 후 사용할 수 있습니다.</p>:<>
      <div className="cma-review-heading"><div><h3>잔고 확인부터 시작하세요</h3><p>조회 → 차이 확인 → 필요한 경우 반영</p></div><span>기록한 이자 합계 <strong>{formatKRW(Number(data.interest_total_krw || 0))}</strong></span></div>
      {pending?<div role="alert"><p>이전 이자 저장 결과를 확인해야 합니다. 같은 요청으로 결과를 확인한 뒤 계속할 수 있습니다.</p><button className="btn btn-primary" disabled={busy||disabled||!canWrite} onClick={()=>apply()}>같은 이자 요청의 결과 확인</button></div>:<fieldset disabled={busy||disabled} className="cma-review-fields">
        <div className="cma-review-toolbar"><label>확인할 CMA 계좌<select className="input-select" aria-label="CMA 이자 계좌" value={aid} onChange={e=>select(e.target.value)}><option value="">계좌 선택</option>{data.accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label><button type="button" className="btn btn-secondary" disabled={!aid} onClick={check}>{observation?'잔고 다시 확인':'NH CMA 잔고 확인'}</button></div>
        {aid && <div className={`cma-balance-review cma-balance-review--${review.tone}`}>
          <div className="cma-balance-numbers"><div><span>앱에 기록된 잔고</span><strong>{money(review.book)}</strong></div><div><span>NH 조회 잔고 {review.target==null && observation && <small>· 확인 전</small>}</span><strong>{money(review.observed)}</strong></div>{review.delta!=null && <div><span>잔고 차이</span><strong>{review.delta>0?'+':''}{money(review.delta)}</strong></div>}</div>
          <p className="cma-review-title" role="status">{review.title}</p><p>{review.description}</p>
          {observation && <small>조회 시각 {new Date(observation.observed_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})}</small>}
          {!review.interestReady && observation && (review.delta!==0) && <div className="cma-review-actions">
            {observation.state==='ZERO_UNVERIFIED' && onReturnToInput && <button type="button" className="btn btn-primary" onClick={onReturnToInput}>누락된 이체부터 입력하기</button>}
            {onReviewBalance && observation.state!=='ZERO_UNVERIFIED' && <button type="button" className="btn btn-primary" onClick={()=>onReviewBalance({accountId:aid,balance:review.target,observedAt:observation.observed_at,reason:'CMA 잔고 차이 확인 · 이자로 확정하지 않은 잔고 차이 정산'})}>잔고 차이 정정하기</button>}
            {onReturnToInput && observation.state!=='ZERO_UNVERIFIED' && <button type="button" className="btn btn-secondary" onClick={onReturnToInput}>입출금·이체 입력으로</button>}
            {onReviewBalance && observation.state==='ZERO_UNVERIFIED' && <details><summary>이체를 모두 기록했는데 잔고가 다른가요?</summary><p>MTS의 실제 잔고를 직접 확인한 뒤 정정할 수 있습니다.</p><button type="button" className="btn btn-secondary" onClick={()=>onReviewBalance({accountId:aid,balance:null,reason:'CMA 실제 잔고 확인 후 잔고 차이 정산'})}>현재 잔고 직접 확인·정정</button></details>}
            <small>정정 화면에서 실제 잔고와 변경액을 확인한 뒤 저장합니다.</small>
          </div>}
        </div>}
        {preview && <>
          {review.interestReady && canWrite && <div className="cma-interest-action"><strong>확인된 지급 이자 {formatKRW(Number(preview.interest_krw))}</strong><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>입출금·이체·매매를 모두 기록했고, 이 금액이 CMA 이자임을 확인했습니다.</label><button type="button" className="btn btn-primary" disabled={!confirmed || Number(preview.interest_krw)<=0} onClick={()=>apply()}>CMA 이자로 반영</button></div>}
          {preview.can_apply===false && <p className="cma-review-note">이자로 자동 반영하지 않았습니다. 잔고 차이 정정과 이자 반영은 각각 확인합니다.</p>}
        </>}
        {!canWrite && <p role="status">이자 반영은 조회 전용 상태입니다. CMA 이자 반영·취소는 서버에서 차단되어 있습니다.</p>}
        <details className="cma-review-details"><summary>상세 조회값·이자 확인 근거</summary>
          {observation && <><p>{cmaStateLabel(observation.state)}</p>{observation.reconciliation && <p>이자 명세 대조: {cmaStateLabel(observation.reconciliation.status)}</p>}
            <div aria-label="CMA 조회 항목"><p>예수금 {observation.cash_krw==null?'확인되지 않음':formatKRW(Number(observation.cash_krw))} · CMA 상품 평가액 {observation.sweep_krw==null?'확인되지 않음':formatKRW(Number(observation.sweep_krw))}</p><p>예수금·CMA 상품 합계 {money(observation.total_krw==null?null:Number(observation.total_krw))}</p><p>출금가능금액 (참고) {observation.withdrawable_krw==null?'확인되지 않음':formatKRW(Number(observation.withdrawable_krw))}</p>{observation.posted_krw!=null && <><p>지급 완료 기준 장부 반영 잔액 {formatKRW(Number(observation.posted_krw))}</p><p>지급 확인 전 평가 차이 {formatKRW(Number(observation.unposted_valuation_krw))} · 이자로 반영하지 않습니다.</p></>}<p>출금가능금액을 계좌 총잔고나 이자 확정액으로 사용하지 않습니다.</p></div></>}
          {preview && <><p>현재 장부 {money(Number(preview.book_krw))} → NH 잔고 {money(Number(preview.broker_krw))} · 잔고 차액 {money(Number(preview.interest_krw))}</p>{preview.can_apply===false && preview.status!=='INITIAL_BALANCE_REVIEW' && <p>{cmaStateLabel(preview.status)}</p>}
          {preview.can_apply===false && preview.status==='INITIAL_BALANCE_REVIEW' && <><p role="alert">{preview.source_start && preview.source_start!==preview.event_date?'조회 기간 지급 이자':'오늘 지급 이자'} {formatKRW(Number(preview.paid_interest_krw))} · 이전 차액 {formatKRW(Number(preview.prior_difference_krw))}. 초기 누적분을 오늘 이자로 합쳐 반영하지 않습니다.</p>
            {canWrite && autoReady && Number(preview.prior_difference_krw)>0 && <details><summary>이전 누적 이자 초기 정리</summary>
              <p>이전 차액만 누적 이자로 기록합니다. 과거 지급일을 추정하지 않고 현재 장부에서 인식하며, 조회 기간의 지급 이자는 별도로 남겨둡니다.</p>
              <label><input type="checkbox" checked={initialConfirmed} onChange={e=>setInitialConfirmed(e.target.checked)}/>입출금은 모두 기록했고 이전 차액은 누적 이자임을 확인했습니다.</label>
              <label>초기 정리 사유<input className="input-text" value={initialReason} maxLength={1000} onChange={e=>setInitialReason(e.target.value)}/></label>
              <button type="button" disabled={!initialConfirmed||initialReason.trim().length<10} onClick={()=>apply(true)}>이전 누적 이자만 정리</button>
            </details>}</>}

          {preview.paid_items?.length>0 && <p>은행 지급일별 이자: {preview.paid_items.map(i=>`${i.event_date} ${formatKRW(Number(i.amount_krw))}`).join(' · ')}</p>}</>}
          <p>이자는 외부 투자금 입금으로 기록하지 않습니다. 과거 지급일이나 금액을 추정하지 않습니다. 기존 과거 기준점과 종가는 자동으로 바꾸지 않습니다.</p>
        </details>
        {aid && <details><summary>매일 확인 설정</summary><p>한국 시간 09:00·12:00·15:40에 하루 최대 3회 확인합니다. 반환 시각을 추정하지 않으며, 자동 반영은 동일한 지급 완료 기준 잔액 두 번 확인과 은행 이자·입출금 명세 대조가 모두 완료된 경우에만 진행합니다. 상품 평가액의 미지급분은 제외합니다. 누락된 지급일은 마지막 반영일부터 최대 30일 범위에서 지급일별로 대조하며, 상한은 각 지급일에 적용합니다.</p>
          <label><input type="checkbox" checked={daily} onChange={e=>setDaily(e.target.checked)}/>매일 CMA 잔고 확인</label>
          <label><input type="checkbox" disabled={!canWrite||!autoReady} checked={automatic} onChange={e=>setAutomatic(e.target.checked)}/>이자 자동 반영 · 검증된 은행 명세와 장부를 대조합니다.</label>
          <label>1일 자동 반영 상한 (원)<input type="number" className="input-number" min="0" max="1000000000" value={limit} onChange={e=>setLimit(e.target.value)}/></label>
          <button type="button" className="btn btn-secondary" onClick={()=>perform(async()=>{const auto=canWrite&&autoReady&&automatic;await api.configureCma(portfolioId,aid,{enabled:daily,auto_apply:auto,max_auto_interest:limit,movements_confirmed:auto});await refresh();setNotice('매일 확인 설정을 저장했습니다.');})}>설정 저장</button>
        </details>}

      </fieldset>}
      <details className="cma-review-details"><summary>이자 기록·자동 확인 설정 안내</summary><p>과거 누적분과 지급일별 이자를 구분합니다. 확인되지 않은 차액은 이자로 자동 반영하지 않습니다.</p>
      <details><summary>최근 이자 반영 이력</summary>{data.income.map(r=><p key={r.id}>{r.event_date} · {formatKRW(Number(r.amount_krw))} {r.reversed_at?'취소됨':<button disabled={busy||disabled||Boolean(pending)||!canWrite} onClick={()=>perform(async()=>{await api.undoCmaIncome(portfolioId,r.account_id,r.id);await refresh();await onChanged?.();})}>이자 기록 취소</button>}</p>)}</details>
      {data.openings?.length>0 && <details><summary>초기 누적 이자 정리 이력</summary>{data.openings.map(r=><p key={r.id}>인식일 {r.recognized_on} · 이전 누적 이자 {formatKRW(Number(r.amount_krw))} · 과거 지급일 미지정 · {r.reason} {r.reversed_at?'취소됨':<button disabled={busy||disabled||Boolean(pending)||!canWrite} onClick={()=>perform(async()=>{await api.undoInitialCmaInterest(portfolioId,r.account_id,r.id);await refresh();await onChanged?.();})}>초기 이자 정리 취소</button>}</p>)}</details>}
      <details><summary>최근 매일 확인 상태</summary>{data.checks.map((r,i)=><p key={i}>{r.event_date} · {r.account_alias} · {cmaStateLabel(r.state)}</p>)}</details>

      </details>
    </>}
  </details>;
}
