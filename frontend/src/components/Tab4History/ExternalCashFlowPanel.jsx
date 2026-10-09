import React, { useEffect, useState } from 'react';
import { api } from '../../utils/api';
import { formatKRW } from '../../utils/formatters';
import { kstToday } from '../../utils/depositMaturities';

export default function ExternalCashFlowPanel({ portfolioId, accounts, performance, onOpenAnalysis, onCashChanged,focused=false,disabled=false }) {
  const { data, busy, error, notice, run, capture } = performance;
  const [applyCash,setApplyCash]=useState(true);
  const [flowChecked, setFlowChecked] = useState(false);
  useEffect(() => { setFlowChecked(false); }, [data]);
  const [form, setForm] = useState(() => ({ request_id: crypto.randomUUID(), account_id: '', event_date: kstToday(), direction: 'DEPOSIT', currency: 'KRW', native_amount: '', exchange_rate: 1400, notes: '' }));
  const change = (key, value) => { setForm(f => ({ ...f, [key]: value })); setFlowChecked(false); };
  const submit = async e => {
    e.preventDefault();
    await run(async () => {
      if (form.currency==='KRW' && applyCash) {
        const context=await api.getNhNoticeContext(portfolioId,form.event_date);
        const account=context.accounts.find(a=>String(a.id)===form.account_id);
        if(!account)throw new Error('계좌를 확인해주세요.');
        await api.commitNhNotices(portfolioId,{request_id:form.request_id,confirmed:true,
          expected_cash:{[form.account_id]:{deposit_krw:Number(account.deposit_krw),deposit_usd:Number(account.deposit_usd)}},
          rows:[{kind:form.direction,account_id:form.account_id,event_date:form.event_date,krw_amount:Number(form.native_amount),notes:form.notes}]});
      } else {
        await api.addPerformanceFlow(portfolioId, { ...form, native_amount: Number(form.native_amount), exchange_rate: form.currency === 'KRW' ? 1 : Number(form.exchange_rate) });
      }
      // Clear only after the server confirms the flow, even if capture/read fails.
      setForm(f => ({ ...f, request_id: crypto.randomUUID(), native_amount: '', notes: '' }));
      setFlowChecked(false);
      if (form.currency==='KRW' && applyCash) await onCashChanged?.();
      await capture();
    });
  };
  const nativeAmount = Number(form.native_amount);
  const validFlow = accounts.some(a => String(a.id) === form.account_id) && flowChecked && Number.isFinite(nativeAmount) && nativeAmount > 0
    && (form.currency === 'KRW' || (Number.isFinite(Number(form.exchange_rate)) && Number(form.exchange_rate) > 0));
  return <section className={`section-card workflow-panel ${focused?'history-focused':''}`}>{focused && <div className="history-section-heading"><h3>외부 투자자금 입출금</h3></div>}<details open={focused || undefined}>
    <summary className={focused?'history-hidden-summary':''} style={{ cursor: 'pointer', fontWeight: 700 }}>🏦 외부 투자자금 입출금 기록</summary>
    {error && <p role="alert">입출금 기록: {error}</p>}{notice && <p>{notice}</p>}
    {!data ? <p>입출금 기록을 조회 중입니다.</p> : !data.tracking ? <div>
      <p>입출금 기록을 시작하려면 7번 ‘분석 및 확인’에서 현재 평가액을 기간 성과 시작 기준으로 등록해주세요.</p>
      <button type="button" className="btn btn-secondary" onClick={onOpenAnalysis}>7. 분석 및 확인으로 이동</button>
    </div> : <div>
        <details className="history-help"><summary>입출금 구분·예수금 반영 안내</summary><p>급여·생활비 계좌 등 이 포트폴리오 밖에서 들어온 투자금과 밖으로 인출한 금액만 기록하세요. 같은 포트폴리오 안의 계좌 이동·매수/매도·환전·배당은 제외합니다. 포트폴리오 간 이동은 양쪽에 각각 기록합니다.</p>
        <p>원화 입출금은 예수금에도 함께 반영할 수 있습니다. 이미 잔고 수정·동기화로 반영했다면 기록만 저장하세요. 달러 입출금은 성과 기록과 5번 탭 달러 관리의 실제 잔고 반영을 함께 확인해주세요.</p></details>
        <form onSubmit={submit}>
          <fieldset disabled={busy || disabled} className="workflow-form">
            <label>입출금 날짜 <input aria-label="입출금 날짜" className="input-text" type="date" min={data.tracking.baseline_date} max={kstToday()} required value={form.event_date} onChange={e=>change('event_date',e.target.value)} /></label>
            <label>입출금 계좌 <select aria-label="입출금 계좌" className="input-select" required value={form.account_id} onChange={e=>change('account_id',e.target.value)}><option value="">계좌 선택</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
            <label>방향 <select aria-label="입출금 방향" className="input-select" value={form.direction} onChange={e=>change('direction',e.target.value)}><option value="DEPOSIT">외부에서 입금</option><option value="WITHDRAW">외부로 출금</option></select></label>
            <label>통화 <select aria-label="입출금 통화" className="input-select" value={form.currency} onChange={e=>change('currency',e.target.value)}><option value="KRW">원화</option><option value="USD">달러</option></select></label>
            <label>입출금 금액 <input aria-label="입출금 금액" className="input-number" type="number" min="0.00000001" step="any" required value={form.native_amount} onChange={e=>change('native_amount',e.target.value)} /></label>
            {form.currency==='USD' && <label>입출금 당시 평가환율 <input aria-label="입출금 당시 평가환율" className="input-number" type="number" min="0.01" step="any" required value={form.exchange_rate} onChange={e=>change('exchange_rate',e.target.value)} /></label>}
            {form.currency==='KRW' && <label>예수금 반영 <select className="input-select" value={applyCash?'APPLY':'REFLECTED'} onChange={e=>{setApplyCash(e.target.value==='APPLY');setFlowChecked(false);}}><option value="APPLY">예수금에도 입출금 반영</option><option value="REFLECTED">잔고에 이미 반영됨 · 기록만 저장</option></select></label>}
            <label>메모 <input aria-label="입출금 메모" className="input-text" maxLength={2000} value={form.notes} onChange={e=>change('notes',e.target.value)} /></label>
            <p>기록할 원화 환산액: {formatKRW(nativeAmount*(form.currency==='USD' ? Number(form.exchange_rate) : 1))}</p>
            <label className="workflow-wide"><input type="checkbox" checked={flowChecked} onChange={e=>setFlowChecked(e.target.checked)} />외부 입출금이며, 선택한 예수금 반영 방식과 기존 기록 중복 여부를 확인했습니다.</label>
            <button className="btn btn-primary" type="submit" disabled={!validFlow}>외부 입출금 기록 저장</button>
          </fieldset>
        </form>
        {!focused && <details><summary>입출금 기록 확인 · {data.flows.filter(f=>!f.voided).length}건</summary>{data.flows.map(f=><p key={f.id}>{f.event_date} · {accounts.find(a=>a.id===f.account_id)?.account_alias || '삭제된 계좌'} · {f.amount_krw>0 ? '입금' : '출금'} {formatKRW(Math.abs(f.amount_krw))} · {f.native_amount} {f.currency} · {f.notes} {f.voided && '(취소됨)'} <button className="btn btn-secondary btn-sm" disabled={busy || disabled} onClick={()=>run(()=>api.voidPerformanceFlow(portfolioId,f.id,!f.voided))}>{f.voided ? '기록 복원' : '기록 취소'}</button></p>)}</details>}
        <details className="history-help"><summary>기록 취소·복원 안내</summary><p>성과 기록만 저장한 입출금의 취소·복원은 예수금을 변경하지 않습니다. 예수금과 함께 반영한 입출금은 NH 알림 가져오기의 반영 이력에서 묶음 취소하세요. 잔고 수정·계좌/보유종목 추가/삭제로 외부 자산이 이동했다면 그 금액 역시 입출금으로 기록해야 합니다.</p></details>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenAnalysis}>7. 분석 및 확인에서 기간 성과 확인</button>
    </div>}
  </details></section>;
}
