import React, {useState} from 'react';
import {ArrowRight, Check, ClipboardPaste, ListChecks} from 'lucide-react';
import {investmentProgress} from '../../utils/investmentProgress';
import {formatKRW, formatUSD, formatQuantity} from '../../utils/formatters';
import './ExecutionTab.css';

const trade = step => ['BUY','SELL'].includes(step.kind);
const amount = (step, value) => trade(step) ? formatQuantity(value, step.unit || '주')
  : step.currency === 'USD' ? formatUSD(value) : formatKRW(value);
const stateName = item => item.review ? '확인 필요' : item.complete ? '완료' : item.excluded ? '제외'
  : item.partial ? '일부 기록됨' : item.ready ? '진행 가능' : '준비 대기';

export default function ExecutionTab({cycle, onOpenPlans, onRecord, onReview, onCloseCycle, renderInput, renderExistingRecords, recordingStepId, onInputClosed, onExistingOpened, compactWhileInput=false, disabled=false}) {
  const [inputStepId, setInputStepId] = useState(null);
  const [inputMode, setInputMode] = useState('record');
  const progress = investmentProgress(cycle);
  const effectiveInputId=inputMode==='existing' || recordingStepId===undefined?inputStepId:recordingStepId;
  const inputStep = progress.steps.find(item => item.step.id === effectiveInputId)?.step;
  const openInput = step => {setInputMode('record');setInputStepId(step.id); onRecord?.(step);};
  const openExisting = step => {setInputMode('existing');setInputStepId(step.id);onExistingOpened?.();};
  const closeInput = () => {setInputStepId(null);setInputMode('record');onInputClosed?.();};
  if (!cycle) return <section className="section-card execution-empty">
    <ListChecks size={32} aria-hidden="true"/><h2>이번 투자를 함께 진행하세요</h2>
    <p>계획에 따라 입금·이체·매수·환전을 기록하고, 다음 접속에서 이어갈 수 있습니다.</p>
    <button className="btn btn-primary" onClick={onOpenPlans} disabled={!onOpenPlans}>리밸런싱 계획 보기 <ArrowRight size={16}/></button>
  </section>;

  const current = progress.current;
  return <div className="execution-tab">
    {(!compactWhileInput || !inputStep) && <section className="section-card execution-heading">
      <div className="execution-title"><span className="execution-eyebrow">투자 회차</span><h2>{cycle.name}</h2>
        <p>{cycle.portfolio_name} · {cycle.status==='CLOSED' ? '종료됨' : cycle.status==='PAUSED' ? '일시 중단' : '진행 중'}</p></div>
      <div className="execution-budget"><span>계획 예산</span><strong>{formatKRW(cycle.budget_krw)}</strong></div>
      <div className="execution-overall"><span>작업 {progress.complete.length} / {progress.total} 완료</span>
        <progress value={progress.complete.length} max={Math.max(1,progress.total)} aria-label="투자 작업 진행률"/>
        <span>{progress.remaining.length ? `남은 작업 ${progress.remaining.length}건` : '모든 작업이 기록되었습니다'}</span></div>
    </section>}

    {inputStep && (inputMode==='record' ? renderInput : renderExistingRecords) ? <section className="section-card execution-input" aria-label="투자 결과 입력">
      <header><div><span className="execution-eyebrow">{inputMode==='existing'?'기록한 거래 가져오기':trade(inputStep)?'새 체결 내역 입력':'새 실행 내역 입력'}</span><h3>{inputStep.title}</h3>
        <p>{inputStep.account_alias}{inputStep.asset_name && ` · ${inputStep.asset_name}`}</p></div>
        <button className="btn btn-secondary btn-sm" disabled={disabled} onClick={closeInput}>투자 진행으로 돌아가기</button></header>
      <p className="execution-cycle-caption">투자 회차 · {cycle.name}</p>
      <div className="execution-quantities">{progress.steps.filter(item=>item.step.id===inputStep.id).map(item=><React.Fragment key={item.step.id}><div><span>계획</span><strong>{amount(inputStep,item.target)}</strong></div><div><span>기록됨</span><strong>{amount(inputStep,item.value)}</strong></div><div><span>남음</span><strong>{amount(inputStep,item.remaining)}</strong></div></React.Fragment>)}</div>
      {inputMode==='existing' ? renderExistingRecords(inputStep, closeInput) : renderInput(inputStep, closeInput)}
    </section> : <section className="section-card execution-current" aria-label="지금 할 일">
      <div className="execution-eyebrow">지금 할 일</div>
      {cycle.status==='CLOSED' ? <><h3>이번 투자를 종료했습니다</h3><p>기록된 결과와 미실행 내역은 아래에서 확인할 수 있습니다.</p></>
        : cycle.status==='PAUSED' ? <><h3>잠시 멈춘 투자입니다</h3><p>기존 기록을 유지하며 나중에 이어갈 수 있습니다.</p></>
        : current ? <>
          <h3>{current.step.title}</h3><p className="execution-account">{current.step.account_alias}{current.step.destination_alias && ` → ${current.step.destination_alias}`}</p>
          {current.step.asset_name && <p className="execution-asset">{current.step.asset_name}</p>}
          <div className="execution-quantities"><div><span>계획</span><strong>{amount(current.step,current.target)}</strong></div>
            <div><span>기록됨</span><strong>{amount(current.step,current.value)}</strong></div>
            <div><span>남음</span><strong>{amount(current.step,current.remaining)}</strong></div></div>
          <p className="execution-guidance">{current.step.instruction || '실제 실행한 내역을 확인한 뒤 기록해주세요.'}</p>
          <p className="execution-entry-hint">증권사에서 실행한 내역을 기록하세요. 5번에 이미 기록했다면 가져오기만 하면 됩니다.</p>
          <button className="btn btn-primary btn-block execution-record" onClick={()=>openInput(current.step)} disabled={disabled || (!renderInput && !onRecord)}>
            <ClipboardPaste size={18}/> {trade(current.step) ? '새 체결 내역 입력' : '새 실행 내역 입력'}</button>
          {renderExistingRecords && <button className="btn btn-secondary btn-block execution-existing" disabled={disabled} onClick={()=>openExisting(current.step)}>기록한 거래 가져오기</button>}
        </> : progress.review.length ? <><h3>기록을 먼저 확인해주세요</h3><p>실행 결과와 장부 반영 여부를 확인해야 다음 단계를 안내할 수 있습니다.</p>
          <button className="btn btn-secondary" onClick={()=>onReview?.(progress.review[0].step)} disabled={!onReview}>기록 확인</button></>
        : progress.remaining.length ? <><h3>앞선 작업의 기록을 기다리고 있습니다</h3><p>남은 작업을 펼쳐 필요한 입금·이체·환전 기록을 확인해주세요.</p></>
        : <><h3>계획한 작업이 모두 기록되었습니다</h3><p>결과를 확인하고 이번 투자를 종료할 수 있습니다.</p>
          <button className="btn btn-primary" disabled={disabled || !onCloseCycle} onClick={onCloseCycle}>이번 투자 종료</button></>}
    </section>}

    {(!compactWhileInput || !inputStep) && <>
    <details className="section-card execution-list"><summary>남은 작업 <span>{progress.remaining.length}건</span></summary>
      {progress.remaining.length === 0 ? <p>남은 작업이 없습니다.</p> : <ol>{progress.remaining.map(item=><li key={item.step.id}>
        <div><strong>{item.step.title}</strong><p>{item.step.account_alias}{item.step.asset_name && ` · ${item.step.asset_name}`}</p>
          <small>{amount(item.step,item.remaining)} 남음</small></div><span className={`execution-state ${item.review?'needs-review':''}`}>{stateName(item)}</span>
        {item.ready && <button className="btn btn-secondary btn-sm" disabled={disabled || (!renderInput && !onRecord)} onClick={()=>openInput(item.step)}>{trade(item.step)?'새 체결 내역 입력':'새 실행 내역 입력'}</button>}{renderExistingRecords && item.ready && <button className="btn btn-secondary btn-sm" disabled={disabled} onClick={()=>openExisting(item.step)}>기록한 거래 가져오기</button>}
        {item.review && <button className="btn btn-secondary btn-sm" disabled={!onReview} onClick={()=>onReview?.(item.step)}>확인</button>}
      </li>)}</ol>}
    </details>

    <details className="section-card execution-list"><summary>완료한 작업 <span>{progress.complete.length}건</span></summary>
      <ul>{progress.complete.map(item=><li key={item.step.id}><Check size={18} aria-hidden="true"/><div><strong>{item.step.title}</strong>
        <p>{item.step.account_alias}{item.step.asset_name && ` · ${item.step.asset_name}`}</p><small>{item.step.satisfied_by_existing_cash ? '기존 잔고로 준비됨' : `${amount(item.step,item.value)} 기록됨`}{item.excess>1e-7 && ` · ${amount(item.step,item.excess)} 초과`}</small></div>
        <span className="execution-state done">완료</span></li>)}</ul>
      {!progress.complete.length && <p>기록이 저장되면 이곳에 표시됩니다.</p>}
    </details>
    <details className="section-card execution-help"><summary>이번 투자 안내</summary>
      <p>입력한 결과는 매매 및 입출금 기록에도 함께 표시됩니다. 기록의 취소·정정은 5번 탭에서 처리합니다.</p>
      <p>계획 저장이나 투자 종료는 잔고를 변경하지 않습니다. 실제 실행한 내역만 확인하여 기록해주세요.</p>
    </details></>}
  </div>;
}
