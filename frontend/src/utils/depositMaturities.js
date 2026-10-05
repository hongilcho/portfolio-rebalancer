export const kstToday = () => new Date(Date.now() + 9 * 3600000).toISOString().slice(0,10);
const day = s => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s || '')) return null;
  const timestamp = Date.parse(s + 'T00:00:00Z');
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0,10) === s ? timestamp / 86400000 : null;
};
export function depositMaturities(assets, accounts, today = kstToday()) {
  const todayDay = day(today);
  return accounts.flatMap(acc => (acc.holdings || []).filter(h => h.is_deposit && h.quantity > 0).map(h => {
    const asset = assets.find(a => String(a.id) === String(h.asset_id)) || h;
    const start = day(asset.start_date), end = day(asset.maturity_date);
    const principal = Number(asset.deposit_principal || 0), quantity = Number(h.quantity);
    const rate = Number(asset.interest_rate || 0), tax = Number(asset.tax_rate ?? 15.4);
    const valid = start !== null && end !== null && end >= start && principal > 0
      && [principal, quantity, rate, tax].every(Number.isFinite) && rate >= 0 && tax >= 0 && tax <= 100;
    const interest = valid ? principal * rate / 100 * (end - start) / 365 : null;
    return { key: `${acc.id}/${h.asset_id}`, name: asset.name || h.asset_name, account: acc.account_alias,
      maturityDate: end === null ? '' : asset.maturity_date,
      daysLeft: end === null || todayDay === null ? null : end - todayDay,
      principal: principal * quantity, rate,
      expectedAmount: valid ? Math.round(principal + interest - Math.floor(interest * tax / 100)) * quantity : null };
  })).sort((a,b) => (a.daysLeft ?? Infinity) - (b.daysLeft ?? Infinity) || a.key.localeCompare(b.key));
}
