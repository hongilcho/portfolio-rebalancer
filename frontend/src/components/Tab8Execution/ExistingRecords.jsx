import React,{useEffect,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW,formatUSD,formatQuantity} from '../../utils/formatters';
export default function ExistingRecords({portfolioId,cycle,step,onUpdated,onClose,onBusyChange}) {
  const [items,setItems]=useState(null),[chosen,setChosen]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{let stop=false;api.getInvestmentCandidates(portfolioId,cycle.id,step.id).then(r=>{if(!stop)setItems(r.items);}).catch(e=>{if(!stop)setError(e.message);});return()=>{stop=true;};},[portfolioId,cycle.id,step.id]);
  const link=async()=>{setBusy(true);onBusyChange(true);try{const item=items.find(r=>r.record_id===chosen);await api.linkInvestmentRecord(portfolioId,cycle.id,{step_id:step.id,revision:cycle.revision,record_kind:item.record_kind,record_id:item.record_id});await onUpdated();onClose();}catch(e){setError(e.message);}finally{setBusy(false);onBusyChange(false);}};
  return <div><p>기존 장부 기록의 연결만 추가합니다. 잔고·수량·원가를 다시 변경하지 않습니다.</p>{error && <p role="alert">{error}</p>}{items===null?<p>기록 조회 중…</p>:!items.length?<p>연결 가능한 기록이 없습니다. 계좌·종목·방향과 등록 시점을 확인해주세요.</p>:<>
    <select aria-label="투자에 연결할 기존 기록" className="input-select" disabled={busy} value={chosen} onChange={e=>setChosen(e.target.value)}><option value="">기록 선택</option>{items.map(r=><option key={r.record_id} value={r.record_id}>{r.event_date} · {r.quantity?formatQuantity(r.quantity,'주'):r.currency==='USD'?formatUSD(r.amount):formatKRW(r.amount)} · {r.record_id.slice(-6)}</option>)}</select>
    <button className="btn btn-primary" disabled={busy || !chosen} onClick={link}>선택 기록 연결</button></>}</div>;
}
