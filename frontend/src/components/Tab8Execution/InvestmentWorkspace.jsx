import React,{useEffect,useState,useRef,useCallback} from 'react';
import ExecutionTab from './ExecutionTab';
import StartInvestment from './StartInvestment';
import GoalEditor from './GoalEditor';
import ExistingRecords from './ExistingRecords';
import {api} from '../../utils/api';
import {formatKRW,formatUSD,formatQuantity} from '../../utils/formatters';
import {investmentProgress} from '../../utils/investmentProgress';
export default function InvestmentWorkspace({portfolioId,model,accounts,usdKrw,selection,inputContext,onRecord,onCloseInput,onOpenPlans,onOpenHistory,onBusyChange,writing}) {
  const [past,setPast]=useState(null),[selected,setSelected]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[reason,setReason]=useState('');
  const chooseSequence=useRef(0);
  const [loadingPast,setLoadingPast]=useState(false);
  const cycle=past || model.cycle;
  const refresh=async()=>{await model.refresh();if(selected)setPast(await api.getInvestment(portfolioId,selected));};
  const choose=useCallback(async id=>{const request=++chooseSequence.current;setSelected(id);setError('');if(!id){setPast(null);setLoadingPast(false);return;}setLoadingPast(true);try{const detail=await api.getInvestment(portfolioId,id);if(request===chooseSequence.current)setPast(detail);}catch(e){if(request===chooseSequence.current)setError(e.message);}finally{if(request===chooseSequence.current)setLoadingPast(false);}},[portfolioId]);
  useEffect(()=>{if(selection?.cycle_id)choose(selection.cycle_id);},[selection?.cycle_id,choose]);
  const state=async status=>{
    if(status==='CLOSED' && !window.confirm('이번 투자를 종료할까요? 실제 장부 기록은 유지됩니다.'))return;
    setBusy(true);onBusyChange(true);setError('');
    try{const id=cycle.id;await api.setInvestmentState(portfolioId,id,{status,reason});onCloseInput();await model.refresh();if(status==='CLOSED'){setSelected(id);setPast(await api.getInvestment(portfolioId,id));}else if(selected)setPast(await api.getInvestment(portfolioId,id));}
    catch(e){setError(e.message);}finally{setBusy(false);onBusyChange(false);}
  };
  const recording=inputContext && cycle && inputContext.cycle_id===cycle.id?inputContext.step.id:null;
  const progress=investmentProgress(cycle),actionBusy=busy || writing || loadingPast;
  const unlink=async result=>{
    if(!window.confirm('투자 작업과의 연결만 해제할까요? 실제 거래와 잔고는 유지됩니다.'))return;
    setBusy(true);onBusyChange(true);
    try{await api.unlinkInvestmentRecord(portfolioId,cycle.id,result.id);await refresh();}catch(e){setError(e.message);}finally{setBusy(false);onBusyChange(false);}
  };
  if(model.available===false)return <section className="section-card"><h2>8. 투자 실행</h2><p role="status">{model.error}</p><button className="btn btn-secondary" onClick={()=>model.refresh().catch(()=>{})}>지원 여부 다시 확인</button></section>;
  return <div className="execution-workspace">
    {(model.error || error) && <p role="alert">{error || model.error}</p>}
    {model.loading && !cycle?<p>투자 과정 조회 중…</p>:!cycle?<><StartInvestment portfolioId={portfolioId} plans={model.plans || []} accounts={accounts} usdKrw={usdKrw} selection={selection} onStarted={async()=>{await model.refresh();setPast(null);setSelected('');}} onBusyChange={onBusyChange}/><button className="btn btn-secondary" onClick={onOpenPlans}>4. 리밸런싱 계획 만들기</button></>:
    <ExecutionTab cycle={cycle} recordingStepId={recording} onInputClosed={onCloseInput} compactWhileInput disabled={actionBusy} onRecord={step=>onRecord(cycle,step)} renderInput={()=>null}
      renderExistingRecords={(step,close)=><ExistingRecords portfolioId={portfolioId} cycle={cycle} step={step} onUpdated={refresh} onClose={close} onBusyChange={onBusyChange}/>}
      onReview={onOpenHistory} onCloseCycle={()=>state('CLOSED')}/>}
    {cycle && !recording && <>
      {cycle.status!=='CLOSED' && <div className="section-card execution-controls"><button className="btn btn-secondary" disabled={actionBusy} onClick={()=>state(cycle.status==='PAUSED'?'ACTIVE':'PAUSED')}>{cycle.status==='PAUSED'?'투자 이어가기':'잠시 중단'}</button>
        <details className="execution-help"><summary>미실행 작업을 남기고 종료</summary><label>종료 이유<input aria-label="투자 종료 이유" className="input-text" maxLength={2000} value={reason} disabled={actionBusy} onChange={e=>setReason(e.target.value)}/></label><p>남은 작업 {progress.remaining.length}건. 종료해도 잔고나 거래를 취소하지 않습니다.</p><button className="btn btn-secondary" disabled={actionBusy || !reason.trim()} onClick={()=>state('CLOSED')}>이유를 남기고 투자 종료</button></details></div>}
      {cycle.status!=='CLOSED' && <GoalEditor key={cycle.id+'/'+cycle.revision} portfolioId={portfolioId} cycle={cycle} onUpdated={refresh} onBusyChange={onBusyChange} disabled={actionBusy}/>}
      <details className="section-card execution-help"><summary>기록 연결과 이번 투자 결과</summary><p>현재 장부 기준입니다. 실제 기록의 취소·정정은 5번에서 처리합니다.</p>
        <ul className="execution-records">{cycle.results.map(r=><li key={r.id}><span>{r.event_date} · {cycle.steps.find(s=>s.id===r.step_id)?.title} · {r.quantity?formatQuantity(r.quantity,'주'):r.currency==='USD'?formatUSD(r.amount):formatKRW(r.amount)}{r.voided?' · 취소/중복':r.ledger_status==='RECORDED'?' · 반영됨':' · 확인 필요'}</span>
          {!r.voided && r.ledger_status==='RECORDED' && cycle.status!=='CLOSED' && <button className="btn btn-secondary btn-sm" disabled={actionBusy} onClick={()=>unlink(r)}>연결만 해제</button>}</li>)}</ul>
        {cycle.report && <p>종료 당시 기록 {(cycle.report.cycle?.results || []).filter(r=>!r.voided && r.ledger_status==='RECORDED').length}건 · 종료 이유 {cycle.report.reason || '전체 작업 완료'}. 이후 취소는 위 현재 기록에 표시됩니다.</p>}
      </details>
    </>}
    {!recording && <details className="section-card execution-help"><summary>지난 투자 보기</summary><select aria-label="지난 투자 선택" className="input-select" value={selected} disabled={actionBusy} onChange={e=>choose(e.target.value)}><option value="">현재 투자 / 새 투자 준비</option>{(model.history || []).map(c=><option key={c.id} value={c.id}>{c.name} · {new Date(c.created_at).toLocaleDateString('ko-KR')} · {c.status==='CLOSED'?'종료':c.status==='PAUSED'?'중단':'진행'}</option>)}</select><button className="btn btn-secondary btn-sm" disabled={actionBusy} onClick={()=>refresh().catch(e=>setError(e.message))}>투자 기록 새로고침</button></details>}
  </div>;
}
