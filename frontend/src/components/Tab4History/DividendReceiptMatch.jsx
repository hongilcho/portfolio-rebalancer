import React,{useEffect,useState} from 'react';
import {api} from '../../utils/api';
export default function DividendReceiptMatch({item,portfolioId,disabled,onMatch}){
 const [open,setOpen]=useState(false),[choices,setChoices]=useState([]),[value,setValue]=useState(''),[error,setError]=useState('');
 useEffect(()=>{if(!open)return;let cancelled=false;
  api.getNhNoticeContext(portfolioId,item.event_date).then(context=>{if(cancelled)return;
   const list=(context.dividend_events||[]).filter(d=>String(d.asset_id)===String(item.detail.asset_id)&&d.ex_date<=item.detail.reference_date).sort((a,b)=>b.ex_date.localeCompare(a.ex_date));
   setChoices(list);const recent=list.filter(d=>Date.parse(item.detail.reference_date)-Date.parse(d.ex_date)<=14*86400000);if(recent.length===1)setValue(recent[0].ex_date);
  }).catch(e=>{if(!cancelled)setError(e.message);});return()=>{cancelled=true;};
 },[open,portfolioId,item]);
 return <div><button type="button" className="btn btn-secondary btn-sm" disabled={disabled} onClick={()=>setOpen(v=>!v)}>배당 손익 연결</button>{open&&<div>
  <p>입금된 예수금은 그대로 두고, 기존 배당 계산액을 실수령액으로 확인합니다.</p>
  <label>연결할 공시 배당<select className="input-select" value={value} disabled={disabled} onChange={e=>setValue(e.target.value)}><option value="">배당 내역 선택</option>{choices.map(d=><option key={d.ex_date} value={d.ex_date}>{d.ex_date} 배당</option>)}</select></label>
  {!choices.length&&<p>아직 연결할 공시 내역이 없습니다. 입금 기록은 그대로 유지됩니다.</p>}
  <button type="button" className="btn btn-primary btn-sm" disabled={disabled||!value} onClick={()=>onMatch(item,value)}>실수령액으로 확인</button>{error&&<p role="alert">{error}</p>}
 </div>}</div>;
}
