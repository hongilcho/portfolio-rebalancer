import React, { useEffect, useState } from 'react';
import { api } from '../../utils/api';
import { formatKRW } from '../../utils/formatters';
import { kstToday } from '../../utils/depositMaturities';

export default function PeriodPerformance({ portfolioId, accounts, dashboardData }) {
  const [data,setData] = useState(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [startChecked,setStartChecked] = useState(false);
  const [flowChecked,setFlowChecked] = useState(false);
  const [completeChecked,setCompleteChecked] = useState(false);
  const [form,setForm] = useState(()=>({request_id:crypto.randomUUID(),account_id:'',event_date:kstToday(),direction:'DEPOSIT',currency:'KRW',native_amount:'',exchange_rate:1400,notes:''}));
  const [open,setOpen] = useState(false);
  const change = (key,value) => {setForm(f=>({...f,[key]:value}));setFlowChecked(false);};
  useEffect(()=>{
    let alive=true;
    (async()=>{
      try {
        let res=await api.getPerformance(portfolioId);
        if (!alive) return;
        if(res.tracking){
          const captured=await api.capturePerformance(portfolioId);
          if(!alive) return;
          setNotice(captured.saved ? '오늘의 최신 조회 평가액을 저장했습니다.' : captured.message);
          res=await api.getPerformance(portfolioId);
        }
        if(alive) {setData(res);setError('');}
      } catch(e) {if(alive) setError(e.message);}
    })();
    return ()=>{alive=false;};
  },[portfolioId,dashboardData]);
  const run = async action => {
    setBusy(true);setError('');
    try {await action();setCompleteChecked(false);} catch(e) {setError(e.message);}
    try {setData(await api.getPerformance(portfolioId));} catch(e) {setError(e.message);}
    setCompleteChecked(false);
    setBusy(false);
  };
  const capture = async () => {const res=await api.capturePerformance(portfolioId);setNotice(res.saved ? '현재 평가액을 저장했습니다.' : res.message);};
  const submit = async e => {
    e.preventDefault();
    await run(async()=>{
      await api.addPerformanceFlow(portfolioId,{...form,native_amount:Number(form.native_amount),exchange_rate:form.currency==='KRW' ? 1 : Number(form.exchange_rate)});
      setForm(f=>({...f,request_id:crypto.randomUUID(),native_amount:'',notes:''}));setFlowChecked(false);
      await capture();
    });
  };
  const nativeAmount=Number(form.native_amount);
  const flowAccount=accounts.find(a=>a.id===form.account_id);
  const validFlow=flowAccount && flowChecked && nativeAmount>0 && Number.isFinite(nativeAmount) && (form.currency==='KRW' || Number(form.exchange_rate)>0);
  const lastSnapshot=data?.snapshots?.at(-1);
  return <section className="section-card workflow-panel">
    <details open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
      <summary style={{cursor:'pointer',fontWeight:700}}>📈 월별·연간 기간 성과 {data?.tracking ? '· 기록 중' : '· 시작 기준 필요'}</summary>
      <p>예수금을 포함한 포트폴리오 전체의 기간 성과를 기록합니다. 기존 보유자산 수익률과 별도 지표입니다.</p>
      {error && <p role="alert">기간 성과: {error}</p>}{notice && <p>{notice}</p>}
      {!data ? <p>기간 성과 정보를 조회 중입니다.</p> : !data.tracking ? <div>
        <p>기준 등록 전 과거 수익률은 재구성하지 않습니다. 등록 후 포트폴리오 현황을 열거나 새로고침하면 그날의 마지막 조회 평가액을 저장합니다. 앱을 사용하지 않은 날짜는 기록되지 않습니다.</p>
        <label><input type="checkbox" checked={startChecked} onChange={e=>setStartChecked(e.target.checked)} />현재 장부의 잔고·예수금·시세를 확인했고, 이후 외부 입출금을 기록하겠습니다.</label>
        <button className="btn btn-primary" disabled={busy || !startChecked} onClick={()=>run(async()=>{await api.startPerformance(portfolioId);setNotice('현재 평가액을 시작 기준으로 등록했습니다.');})}>기간 성과 시작 기준 등록</button>
      </div> : <div>
        <p>시작 기준 {data.tracking.baseline_date} · {formatKRW(data.tracking.baseline_value)} · 평가 기록 {data.snapshots.length}일</p>
        <button className="btn btn-secondary" disabled={busy} onClick={()=>run(capture)}>현재 평가액 다시 기록</button>
        <details><summary>외부 투자자금 입출금 입력</summary>
        <p>급여·생활비 계좌 등 이 포트폴리오 밖에서 들어온 투자금과 밖으로 인출한 금액만 기록하세요. 같은 포트폴리오 안의 계좌 이동·매수/매도·환전·배당은 제외합니다. 포트폴리오 간 이동은 양쪽에 각각 기록합니다.</p>
        <p><strong>이 입력은 성과 계산용 기록만 저장합니다.</strong> 실제 예수금은 기존 잔고 수정·동기화로 별도 반영하세요. 시작 기준 등록 당일에는 기준 등록 이후 발생한 입출금만 기록합니다.</p>
        <form onSubmit={submit}>
          <fieldset disabled={busy} className="workflow-form">
            <label>입출금 날짜 <input aria-label="입출금 날짜" className="input-text" type="date" min={data.tracking.baseline_date} max={kstToday()} required value={form.event_date} onChange={e=>change('event_date',e.target.value)} /></label>
            <label>입출금 계좌 <select aria-label="입출금 계좌" className="input-select" required value={form.account_id} onChange={e=>change('account_id',e.target.value)}><option value="">계좌 선택</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
            <label>방향 <select aria-label="입출금 방향" className="input-select" value={form.direction} onChange={e=>change('direction',e.target.value)}><option value="DEPOSIT">외부에서 입금</option><option value="WITHDRAW">외부로 출금</option></select></label>
            <label>통화 <select aria-label="입출금 통화" className="input-select" value={form.currency} onChange={e=>change('currency',e.target.value)}><option value="KRW">원화</option><option value="USD">달러</option></select></label>
            <label>입출금 금액 <input aria-label="입출금 금액" className="input-number" type="number" min="0.00000001" step="any" required value={form.native_amount} onChange={e=>change('native_amount',e.target.value)} /></label>
            {form.currency==='USD' && <label>입출금 당시 평가환율 <input aria-label="입출금 당시 평가환율" className="input-number" type="number" min="0.01" step="any" required value={form.exchange_rate} onChange={e=>change('exchange_rate',e.target.value)} /></label>}
            <label>메모 <input aria-label="입출금 메모" className="input-text" maxLength={2000} value={form.notes} onChange={e=>change('notes',e.target.value)} /></label>
            <p>기록할 원화 환산액: {formatKRW(nativeAmount*(form.currency==='USD' ? Number(form.exchange_rate) : 1))}</p>
            <label className="workflow-wide"><input type="checkbox" checked={flowChecked} onChange={e=>setFlowChecked(e.target.checked)} />외부 입출금이며, 실제 예수금은 별도 반영했고 기존 입출금 기록과 중복되지 않음을 확인했습니다.</label>
            <button className="btn btn-primary" type="submit" disabled={!validFlow}>외부 입출금 기록 저장</button>
          </fieldset>
        </form>
        </details>
        <details><summary>입출금 기록 확인 · {data.flows.filter(f=>!f.voided).length}건</summary>{data.flows.map(f=><p key={f.id}>{f.event_date} · {accounts.find(a=>a.id===f.account_id)?.account_alias || '삭제된 계좌'} · {f.amount_krw>0 ? '입금' : '출금'} {formatKRW(Math.abs(f.amount_krw))} · {f.native_amount} {f.currency} · {f.notes} {f.voided && '(취소됨)'} <button className="btn btn-secondary btn-sm" disabled={busy} onClick={()=>run(()=>api.voidPerformanceFlow(portfolioId,f.id,!f.voided))}>{f.voided ? '기록 복원' : '기록 취소'}</button></p>)}</details>
        <p>입출금 기록 취소·복원도 예수금을 변경하지 않습니다. 잔고 수정·계좌/보유종목 추가/삭제로 외부 자산이 이동했다면 그 금액 역시 입출금으로 기록해야 합니다.</p>
        <label><input type="checkbox" checked={completeChecked} onChange={e=>setCompleteChecked(e.target.checked)} />시작 기준부터 최근 평가일까지 외부 입출금을 모두 기록했고 실제 잔고도 반영했습니다. 입출금이 없으면 없음으로 확인합니다.</label>
        <button className="btn btn-secondary" disabled={busy || !completeChecked || !lastSnapshot} onClick={()=>run(()=>api.confirmPerformanceFlows(portfolioId,{revision:data.tracking.revision,through:lastSnapshot.snapshot_date,value:Number(lastSnapshot.value_krw)}))}>기간 입출금 기록 확인 완료</button>
        <div className="table-container"><table className="custom-table"><thead><tr><th>구분</th><th>기간</th><th>평가 시작/종료</th><th>순입금</th><th>기간 손익</th><th>금액가중 기간 수익률</th></tr></thead><tbody>
          {data.reports.map(r=><tr key={`${r.kind}/${r.label}`}><td>{r.kind}</td><td>{r.label}{r.partial && ' (기준 등록 이후)'}<br />{r.start} ~ {r.end}</td><td>{r.start_value==null ? '미기록' : formatKRW(r.start_value)} / {r.end_value==null ? '미기록' : formatKRW(r.end_value)}</td><td>{r.net_flow==null ? '—' : formatKRW(r.net_flow)}</td><td>{r.profit==null ? '—' : formatKRW(r.profit)}{r.warning && <p>{r.warning}</p>}</td><td>{r.return_pct==null ? '계산 대기' : `${(Math.abs(r.return_pct)<0.005 ? 0 : r.return_pct).toFixed(2)}%`}</td></tr>)}
        </tbody></table></div>
      </div>}
      <details><summary>계산 방식·기록 범위 안내</summary>
        <p>선택한 포트폴리오의 보유자산·예금·원화/달러 예수금 전체를 원화로 평가합니다. 가상자산과 다른 포트폴리오는 제외합니다.</p>
        <p>배당은 실제 잔고에 반영된 금액으로만 포함합니다. 계산된 배당 손익을 평가액에 다시 더하지 않습니다. 앱에서 조회한 시점의 평가액이며 월말 종가를 보장하지 않습니다.</p>
        <p>기간 손익 = 종료 평가액 − 시작 평가액 − 순입금. 수익률은 날짜별 입출금을 반영한 금액가중 방식(XIRR의 기간 환산)이며 연환산 수익률·시간가중 수익률이 아닙니다. 같은 날의 입출금은 날짜 단위로 계산합니다. 단순 월 수익률 합산으로 연 수익률을 만들지 않습니다.</p>
        <p>월말·연말 경계일 평가액이 없으면 해당 기간을 계산하지 않습니다. 현재 월·연은 최근 기록일까지의 성과입니다. 입력한 현금 흐름·잔고 및 조회 시세의 정확도에 의존합니다.</p>
      </details>
    </details>
  </section>;
}
