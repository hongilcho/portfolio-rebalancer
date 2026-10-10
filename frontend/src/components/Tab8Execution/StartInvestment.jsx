import React,{useEffect,useRef,useState} from 'react';
import {api} from '../../utils/api';
import {canTransferOut} from '../../utils/investmentInput';
import {formatKRW,formatUSD,formatQuantity} from '../../utils/formatters';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,singleSubmission} from '../../utils/bookkeepingRequest';
export default function StartInvestment({portfolioId,plans,accounts,usdKrw,selection,onStarted,onBusyChange}) {
  const key='investment-start/v1/'+portfolioId,lock=useRef(false);
  const [pending,setPending]=useState(()=>readPendingRequest(key));
  const [form,setForm]=useState(()=>pending?.payload || {request_id:crypto.randomUUID(),plan_id:selection?.plan_id || '',representative_account_id:String(accounts.find(canTransferOut)?.id || ''),additional_cash_krw:0,source_limits:{},usd_krw:usdKrw});
  const [preview,setPreview]=useState(null),[checked,setChecked]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{if(selection?.plan_id && !pending){setForm(old=>({...old,plan_id:selection.plan_id}));setPreview(null);setChecked(false);}},[selection?.plan_id,pending]);
  const edit=(field,value)=>{setForm(old=>({...old,[field]:value,request_id:crypto.randomUUID()}));setPreview(null);setChecked(false);};
  const run=action=>singleSubmission(lock,async()=>{setBusy(true);onBusyChange?.(true);setError('');try{await action();}catch(e){setError(e.message);}finally{setBusy(false);onBusyChange?.(false);}});
  const start=()=>run(async()=>{
    const body=pending?.payload || {...form,preview_token:preview.preview_token};
    if(!pending){persistPendingRequest(key,{payload:body});setPending({payload:body});}
    let recorded=false;
    try {const result=await api.createInvestment(portfolioId,body);recorded=true;clearPendingRequest(key);setPending(null);await onStarted(result.id);}
    catch(e){if(!recorded && e.status && e.status<500 && ![401,403,429].includes(e.status)){clearPendingRequest(key);setPending(null);setPreview(null);setChecked(false);}throw recorded?new Error('투자 과정은 저장됐지만 화면 갱신에 실패했습니다. 다시 시작하지 말고 새로고침해주세요.'):e;}
  });
  return <section className="section-card execution-start"><h2>이번 투자 시작</h2>
    <p>이미 입금한 돈은 현재 예수금에 포함됩니다. 앞으로 추가 입금할 금액만 아래에 입력하세요.</p>
    {error && <p role="alert">{error}</p>}
    {pending?<><p>시작 요청의 결과를 확인 중입니다.</p><button className="btn btn-primary" disabled={busy} onClick={start}>같은 시작 요청의 결과 확인</button></>:<>
    <fieldset className="workflow-form" disabled={busy}>
      <label>저장 계획<select aria-label="투자 실행 계획" className="input-select" value={form.plan_id} onChange={e=>edit('plan_id',e.target.value)}><option value="">계획 선택</option>{plans.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>대표 자금 계좌<select aria-label="투자 대표 계좌" className="input-select" value={form.representative_account_id} onChange={e=>edit('representative_account_id',e.target.value)}>{accounts.filter(canTransferOut).map(a=><option key={a.id} value={a.id}>{a.account_alias} · {formatKRW(a.deposit_krw)}</option>)}</select></label>
      <label>앞으로 추가 입금할 금액 (원)<input aria-label="추가 투자 입금액" className="input-number" type="number" min="0" step="1" value={form.additional_cash_krw} onChange={e=>edit('additional_cash_krw',Number(e.target.value))}/></label>
      <label>예상 환율 (원/달러)<input aria-label="투자 예상 환율" className="input-number" type="number" min="0.01" step="any" value={form.usd_krw} onChange={e=>edit('usd_krw',Number(e.target.value))}/></label>
    </fieldset>
    <details className="execution-help"><summary>다른 계좌의 현금도 사용</summary><p>이번 투자에 출금하여 사용할 한도를 지정합니다. 절세계좌의 현금은 해당 계좌 안에서만 사용합니다.</p>{accounts.filter(a=>canTransferOut(a) && String(a.id)!==form.representative_account_id).map(a=><label className="execution-source" key={a.id}>{a.account_alias} · 예수금 {formatKRW(a.deposit_krw)}<input aria-label={a.account_alias+' 사용 한도'} className="input-number" type="number" min="0" step="1" disabled={busy} value={form.source_limits[a.id] || ''} onChange={e=>edit('source_limits',{...form.source_limits,[a.id]:Number(e.target.value)})}/></label>)}</details>
    <button className="btn btn-secondary" disabled={busy || !form.plan_id || !form.representative_account_id || form.usd_krw<=0} onClick={()=>run(async()=>setPreview(await api.prepareInvestment(portfolioId,form)))}>필요한 작업 미리 확인</button>
    {preview && <div className="execution-start-review"><h3>이번 투자에 필요한 작업</h3><ul>{preview.steps.map(s=><li key={s.key}><strong>{s.title}</strong> · {s.account_alias}{s.destination_alias && ' → '+s.destination_alias} · {s.kind==='BUY'?formatQuantity(s.target_quantity,'주'):s.currency==='USD'?formatUSD(s.target_amount):formatKRW(s.target_amount)}</li>)}</ul>
      <p>장부 잔고와 예상 단가 기준입니다. 실제 입금·이체·환전·매수는 직접 진행합니다.</p>
      <label><input aria-label="투자 준비 계획 확인" type="checkbox" checked={checked} disabled={busy} onChange={e=>setChecked(e.target.checked)}/>자금 사용 범위와 목표를 확인했습니다.</label>
      <button className="btn btn-primary btn-block" disabled={busy || !checked} onClick={start}>확인한 계획으로 투자 시작</button>
    </div>}</>}
  </section>;
}
