export const kstToday = () => new Date(Date.now() + 9 * 3600000).toISOString().slice(0,10);
const day = s => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s || '')) return null;
  const timestamp = Date.parse(s + 'T00:00:00Z');
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0,10) === s ? timestamp / 86400000 : null;
};
export function depositMaturities(assets, accounts, today = kstToday()) {
  const todayDay = day(today);
  // Pure deposits are master assets, even without a holding row. Match NAV:
  // each positive principal is counted once rather than once per account.
  return assets.filter(a => a.is_deposit && Number(a.deposit_principal)>0).map(asset => {
    const holder = accounts.find(acc => (acc.holdings || []).some(h => String(h.asset_id)===String(asset.id) && h.quantity>0));
    const start = day(asset.start_date), end = day(asset.maturity_date);
    const principal = Number(asset.deposit_principal || 0);
    const rate = Number(asset.interest_rate || 0), tax = Number(asset.tax_rate ?? 15.4);
    const valid = start !== null && end !== null && end >= start && principal > 0
      && [principal, rate, tax].every(Number.isFinite) && rate >= 0 && tax >= 0 && tax <= 100;
    const interest = valid ? principal * rate / 100 * (end - start) / 365 : null;
    return { key: String(asset.id), name: asset.name, account: asset.account_no || holder?.account_alias || '등록 예금',
      maturityDate: end === null ? '' : asset.maturity_date,
      daysLeft: end === null || todayDay === null ? null : end - todayDay,
      principal, rate,
      expectedAmount: valid ? Math.round(principal + interest - Math.floor(interest * tax / 100)) : null };
  }).sort((a,b) => (a.daysLeft ?? Infinity) - (b.daysLeft ?? Infinity) || a.key.localeCompare(b.key));
}
