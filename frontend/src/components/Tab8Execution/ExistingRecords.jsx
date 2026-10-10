import React,{useEffect,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW,formatUSD,formatQuantity} from '../../utils/formatters';
export default function ExistingRecords({portfolioId,cycle,step,onUpdated,onClose,onBusyChange}) {
  const [items,setItems]=useState(null),[chosen,setChosen]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{let stop=false;setItems(null);setChosen('');setError('');api.getInvestmentCandidates(portfolioId,cycle.id,step.id).then(r=>{if(!stop)setItems(r.items);}).catch(e=>{if(!stop)setError(e.message);});return()=>{stop=true;};},[portfolioId,cycle.id,step.id]);
  const link=async()=>{setBusy(true);onBusyChange(true);try{const item=items.find(r=>r.record_id===chosen);await api.linkInvestmentRecord(portfolioId,cycle.id,{step_id:step.id,revision:cycle.revision,record_kind:item.record_kind,record_id:item.record_id});await onUpdated();onClose();}catch(e){setError(e.message);}finally{setBusy(false);onBusyChange(false);}};
  return <div className="execution-existing-picker">
    <p className="execution-save-note">5번 장부에 기록한 거래를 이번 투자 회차에 연결합니다. 예수금과 보유 수량은 다시 변경하지 않습니다.</p>
    {error && <p role="alert">{error}</p>}
    {items===null?<p>기록 조회 중…</p>:!items.length?<p>이 작업에 연결할 수 있는 거래가 없습니다. 먼저 5번에서 기록하거나 ‘새 체결 내역 입력’을 이용해주세요.</p>:<>
      <fieldset disabled={busy}><legend>연결할 거래 선택</legend>
        {items.map(r=><label className="execution-candidate" key={r.record_kind+'/'+r.record_id}>
          <input type="radio" name="execution-record" aria-label={`거래 ${r.event_date} ${r.quantity || r.amount}`} value={r.record_id} checked={chosen===r.record_id} onChange={()=>setChosen(r.record_id)}/>
          <span><strong>{r.event_date} · {r.quantity?formatQuantity(r.quantity,'주'):r.currency==='USD'?formatUSD(r.amount):formatKRW(r.amount)}</strong>
            <small>{step.account_alias}{step.asset_name && ` · ${step.asset_name}`}</small>
            {Number(r.price)>0 && <small>체결 단가 · {r.currency==='USD'?formatUSD(Number(r.price)):formatKRW(Number(r.price))}</small>}
            <small>거래 번호 끝 6자리 · {r.record_id.slice(-6)}</small></span>
        </label>)}
      </fieldset>
      <button className="btn btn-primary btn-block" disabled={busy || !chosen} onClick={link}>{busy?'연결 중…':'이번 투자 회차에 연결'}</button>
    </>}
  </div>;
}
