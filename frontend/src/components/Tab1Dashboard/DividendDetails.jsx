import React, { useState } from 'react';
import { dividendGroups } from '../../utils/dividendDetails';
import { formatKRW, formatUSD, formatQuantity } from '../../utils/formatters';

export default function DividendDetails({ accounts }) {
  const [selected, setSelected] = useState('all');
  const groups = dividendGroups(accounts);
  if (!groups.length) return null;
  const visible = selected === 'all' ? groups : groups.filter(g => g.accountId === selected);
  const totals = visible.reduce((sum,g) => ({...sum,[g.currency]:sum[g.currency]+g.reflected}),{KRW:0,USD:0});
  return <div className="section-card"><details>
    <summary style={{cursor:'pointer',fontWeight:700}}>💰 배당 계산 상세 보기 · {groups.length}개 계좌·종목</summary>
    <p>배당락일 당시 수량과 수집된 주당 배당금으로 계산한 내역입니다. 실제 입금일·지급액 확인 기록이 아니며 예수금을 변경하지 않습니다. 과거 거래 누락이나 잔고 기준 수정에 따라 계산 범위가 달라질 수 있습니다.</p>
    <label>계좌 필터 <select className="input-select" aria-label="배당 내역 계좌" value={selected} onChange={e=>setSelected(e.target.value)}>
      <option value="all">전체 계좌</option>{accounts.filter(a => groups.some(g => g.accountId === String(a.id))).map(a => <option key={a.id} value={a.id}>{a.account_alias}</option>)}
    </select></label>
    <p>손익에 반영된 배당: 원화 {formatKRW(totals.KRW)} · 달러 {formatUSD(totals.USD)} (통화별 합계)</p>
    {visible.map(g => { const money = g.currency === 'USD' ? formatUSD : formatKRW;
      return <div className="trade-row-card" key={g.key}>
        <b>{g.name} · {g.account} · {g.currency}</b>
        <p>계산 내역 합계 {money(g.calculated)} · 손익 반영액 {money(g.reflected)}</p>
        {g.adjusted && <p>내역 합계와 반영액이 다릅니다. 수동 배당 보정값 및 과거 거래 기준을 확인해주세요.</p>}
        {!g.details.length ? <p>표시할 배당락일별 계산 내역이 없습니다.</p> : <div className="table-container"><table className="custom-table">
          <thead><tr><th>배당락일</th><th>당시 수량</th><th>주당 배당</th><th>세전 계산액</th><th>계산 세금</th><th>세후 계산액</th></tr></thead>
          <tbody>{g.details.map((d,i) => <tr key={`${d.ex_date}/${i}`}><td>{d.ex_date}</td><td>{formatQuantity(d.holding_quantity,'주')}</td><td>{`${Number(d.amount_per_share || 0).toLocaleString('ko-KR',{maximumFractionDigits:6})} ${g.currency === 'USD' ? '달러' : '원'}`}</td><td>{money(d.gross_amount)}</td><td>{money(d.tax_amount)}</td><td>{money(d.net_amount)}</td></tr>)}</tbody>
        </table></div>}
      </div>;
    })}
  </details></div>;
}
