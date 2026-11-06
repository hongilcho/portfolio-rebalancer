import { marketStatusRows } from '../../utils/marketStatus';

export default function MarketStatus({ status }) {
  const rows = marketStatusRows(status);
  const missing=status?.dividends?.incomplete_symbols||[];
  if(missing.length)rows.push(`${missing.join(', ')} 배당 자료 누락 가능 · 0원으로 확정하지 말고 NH 입금 알림을 확인해주세요.`);
  if (!rows.length) return null;
  return <div role="status" style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', lineHeight: 1.6 }}>
    {rows.map(row => <div key={row}>{row}</div>)}
  </div>;
}
