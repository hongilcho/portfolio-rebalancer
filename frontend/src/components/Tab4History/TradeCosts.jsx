import React from 'react';
import {estimateFee} from '../../utils/tradingFees';
import {kstToday} from '../../utils/depositMaturities';
export default function TradeCosts({row,isUS,onChange,account,asset,day=kstToday(),tradeType='BUY'}){
  const fee=estimateFee(account,asset,day,row.quantity,row.price);
  const gross=Number(row.quantity)*Number(row.price)||0;
  const value=row.costsConfirmed?Number(isUS?row.feesUsd:row.feesKrw)||0:fee?.amount;
  const format=v=>isUS?`$${v.toFixed(2)}`:`${v.toLocaleString()}원`;
  return <><p className="fee-trade-summary">{row.costsConfirmed?'확인한 비용':fee?'자동 계산 · 예상 수수료':'수수료율 미설정'}{value!=null&&` ${format(value)} · ${tradeType==='SELL'?'예상 수령액':'예상 차감액'} ${format(gross+(tradeType==='SELL'?-value:value))}`}</p>
  <details className="history-help"><summary>수수료·실제 차감 세금 확인 / 변경</summary>
    <label className="history-check"><input type="checkbox" checked={Boolean(row.costsConfirmed)} onChange={e=>onChange('costsConfirmed',e.target.checked)}/>비용을 확인했습니다 · 없으면 0</label>
    {row.costsConfirmed?<div className="history-filters">
      {isUS&&<label>달러 비용 합계<input className="input-number" type="number" min="0" step="0.0001" value={row.feesUsd??0} onChange={e=>onChange('feesUsd',e.target.value)}/></label>}
      <label>원화 비용 합계<input className="input-number" type="number" min="0" step="0.01" value={row.feesKrw??0} onChange={e=>onChange('feesKrw',e.target.value)}/></label>
      <small>입력한 비용은 예수금에서 함께 차감됩니다. 단가에 이미 포함한 비용을 중복 입력하지 마세요.</small>
    </div>:<p className="history-muted">계좌에 설정한 수수료를 자동 반영합니다. 미설정이어도 거래는 저장하며, 잔고가 부족한 예상 비용은 정산 대기로 남깁니다. 나중에 예수금 차이를 정산할 수 있습니다. 매도 세금은 별도 확인이 필요합니다.</p>}
  </details></>;
}
