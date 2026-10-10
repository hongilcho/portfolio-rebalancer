import React from 'react';
import {formatKRW,formatUSD} from '../../utils/formatters';
export default function FundingDetails({rows=[]}){
 if(!rows.length)return null;
 return <details className="execution-help"><summary>예수금과 여유분을 반영한 자금 계산</summary>{rows.map(row=><div className="trade-row-card" key={row.account_id}><strong>{row.account_alias}</strong>
 <p>예상 매수액 {formatKRW(row.estimated_buy_krw)} · 가격 여유 {formatKRW(row.price_buffer_krw)} · 환율 여유 {formatKRW(row.fx_buffer_krw)}</p>
 <p>기존 예수금 {formatKRW(row.existing_krw)} / {formatUSD(row.existing_usd)} · 달러를 고려한 필요 원화 {formatKRW(row.required_krw)}</p></div>)}</details>;
}
