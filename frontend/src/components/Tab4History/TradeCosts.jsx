import React from 'react';
export default function TradeCosts({row,isUS,onChange}){
  return <details className="history-help"><summary>수수료·실제 차감 세금</summary>
    <label className="history-check"><input type="checkbox" checked={Boolean(row.costsConfirmed)} onChange={e=>onChange('costsConfirmed',e.target.checked)}/>비용을 확인했습니다 · 없으면 0</label>
    {row.costsConfirmed?<div className="history-filters">
      {isUS&&<label>달러 비용 합계<input className="input-number" type="number" min="0" step="0.0001" value={row.feesUsd??0} onChange={e=>onChange('feesUsd',e.target.value)}/></label>}
      <label>원화 비용 합계<input className="input-number" type="number" min="0" step="0.01" value={row.feesKrw??0} onChange={e=>onChange('feesKrw',e.target.value)}/></label>
      <small>입력한 비용은 예수금에서 함께 차감됩니다. 단가에 이미 포함한 비용을 중복 입력하지 마세요.</small>
    </div>:<p className="history-muted">미입력 시 거래는 저장하며 순손익은 비용 확인 전으로 표시합니다.</p>}
  </details>;
}
