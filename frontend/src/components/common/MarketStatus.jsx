import { marketStatusRows } from '../../utils/marketStatus';

export default function MarketStatus({ status }) {
  const rows = marketStatusRows(status);
  if (!rows.length) return null;
  return <div role="status" style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', lineHeight: 1.6 }}>
    {rows.map(row => <div key={row}>{row}</div>)}
  </div>;
}
