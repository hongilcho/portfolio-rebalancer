import React,{useState} from 'react';
import '../common/TradingFees.css';
import {feeLabels,setFeePolicy} from '../../utils/tradingFees';
import {kstToday} from '../../utils/depositMaturities';

export default function AccountFees({value,onChange}){
  const schedule=typeof value==='string'?JSON.parse(value):value||{};
  const [day,setDay]=useState(kstToday());
  return <fieldset className="fee-settings"><legend>거래 수수료 자동 계산</legend>
    <p className="history-muted">한 번 설정하면 매수·매도에 자동 적용합니다. 공란은 미설정, 0은 수수료 없음입니다.</p>
    <label>새 요율 적용 시작일<input type="date" className="input-text" value={day} onChange={e=>setDay(e.target.value)}/></label>
    {Object.entries(feeLabels).map(([key,label])=>{
      const selected=(schedule[key]||[]).filter(e=>e.from<=day).at(-1);
      const change=(field,next)=>onChange(setFeePolicy(schedule,key,{...(selected||{}),from:day,rate_pct:selected?.rate_pct??'',vat_included:selected?.vat_included??true,note:selected?.note||'',[field]:next}));
      return <div className="fee-setting-row" key={key}>
        <label>{label} 수수료율 (%)<input className="input-number" type="number" min="0" max="10" step="0.0000001" placeholder="미설정" value={selected?.rate_pct??''} onChange={e=>change('rate_pct',e.target.value)}/></label>
        {key==='GOLD'&&<label><input type="checkbox" checked={selected?.vat_included??true} onChange={e=>change('vat_included',e.target.checked)}/>입력 요율에 수수료 부가세 포함</label>}
        {key==='US'&&<input className="input-text" aria-label="미국 수수료 메모" maxLength="200" placeholder="예: 나무멤버스 유지 · 0.07%" value={selected?.note||''} onChange={e=>change('note',e.target.value)}/>}
        {!!schedule[key]?.length&&<details><summary>적용 이력</summary>{schedule[key].map(e=><p key={e.from}>{e.from}부터 {e.rate_pct==null?'미설정':`${e.rate_pct}%`} {e.note}</p>)}</details>}
      </div>;
    })}
    <small>자동 계산은 예상 비용입니다. 매도 관련 세금은 별도로 확인합니다. 과거 거래의 비용은 설정 변경으로 다시 계산하지 않습니다.</small>
  </fieldset>;
}
