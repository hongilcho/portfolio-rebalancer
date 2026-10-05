import React from 'react';
import { depositMaturities } from '../../utils/depositMaturities';
import { formatKRW } from '../../utils/formatters';

export default function DepositMaturities({ assets, accounts }) {
  const items = depositMaturities(assets, accounts);
  if (!items.length) return <div className="section-card"><h3>📅 예금 만기 안내</h3><p>등록된 예금이 없습니다.</p></div>;
  const imminent = items.filter(i => i.daysLeft !== null && i.daysLeft <= 30).length;
  return <div className="section-card"><details>
    <summary style={{ cursor:'pointer',fontWeight:700 }}>📅 예금 만기 안내 · 보유 {items.length}건 · 만기 경과/30일 이내 {imminent}건</summary>
    <p>예상 금액은 등록한 금리·세율과 일할이자(365일)를 사용한 계산치이며, 실제 지급액은 은행에서 확인하세요.</p>
    {items.map(item => <div className="trade-row-card" key={item.key}>
      <b>{item.name} · {item.account}</b>
      <p>만기일 {item.maturityDate || '미등록/확인 필요'} · {item.daysLeft === null ? '만기일 확인 필요' : item.daysLeft < 0 ? `만기 ${-item.daysLeft}일 경과` : item.daysLeft === 0 ? '오늘 만기' : `D-${item.daysLeft}`}</p>
      <p>원금 {formatKRW(item.principal)} · 연 {item.rate}% · 예상 세후 만기금액 {item.expectedAmount === null ? '조건 확인 필요' : formatKRW(item.expectedAmount)}</p>
      {item.daysLeft !== null && item.daysLeft <= 0 && <p>만기 처리 여부와 실제 예수금을 확인해주세요. 자동으로 장부를 변경하지 않습니다.</p>}
    </div>)}
  </details></div>;
}
