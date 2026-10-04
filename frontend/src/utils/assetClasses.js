// Shared classification for individual holdings, overview charts and table order.
const BOND_TICKERS = new Set([
  '0085P0', '476760', 'SGOV', 'BIL', 'SHV', 'TLT', 'IEF', 'SHY', 'BND', 'AGG',
  '488770', '453650',
]);
const BOND_NAMES = [
  '국채', '채권', 'bond', 'treasury', '머니마켓', '단기자금', '단기채',
  'kofr', 'cd금리', 'money market', 'fixed income',
];
const DEPOSIT_NAMES = ['예금', '적금', '새마을', '금고'];
const ALTERNATIVE_NAMES = ['금99', '금 99', '원자재', 'gold', 'commodity'];

const CLASSES = {
  equity: { label: '📈 주식', color: '#3B82F6', order: 0 },
  bonds: { label: '📜 채권', color: '#8B5CF6', order: 1 },
  gold_commodities: { label: '🥇 대체투자', color: '#EAB308', order: 2 },
  deposits: { label: '🏦 예금', color: '#10B981', order: 3 },
  crypto: { label: '🪙 가상화폐', color: '#F97316', order: 4 },
  cash: { label: '💵 예수금', color: '#64748B', order: 5 },
};

export function classifyAsset(item) {
  const name = String(item?.name || '').trim().toLowerCase();
  const ticker = String(item?.ticker || '').trim().toUpperCase();
  const market = String(item?.market || '').trim().toUpperCase();
  const assetType = String(item?.asset_type || '').trim().toUpperCase();

  if (item?.is_deposit || assetType === 'DEPOSIT' || ticker.startsWith('DEP') ||
      DEPOSIT_NAMES.some(token => name.includes(token))) {
    return 'deposits';
  }
  if (assetType === 'CRYPTO' || market === 'CRYPTO') return 'crypto';
  if (ticker === 'PDBC' || ticker === 'M04020000' ||
      ALTERNATIVE_NAMES.some(token => name.includes(token))) {
    return 'gold_commodities';
  }
  if (BOND_TICKERS.has(ticker) || BOND_NAMES.some(token => name.includes(token))) {
    return 'bonds';
  }
  return 'equity';
}

export function sortInvestmentAssets(assets) {
  // Evaluate classification once per asset and keep the input array untouched.
  return (assets || []).map(asset => ({
    asset,
    order: CLASSES[classifyAsset(asset)].order,
    value: Number(asset.eval_amount) || 0,
  })).sort((a, b) => a.order - b.order || b.value - a.value)
    .map(row => row.asset);
}

export function assetClassBreakdown(assets, valueKey, { includeCrypto = false, cashKrw } = {}) {
  const totals = Object.fromEntries(Object.entries(CLASSES)
    .filter(([key]) => (key !== 'crypto' || includeCrypto) && (key !== 'cash' || cashKrw !== undefined))
    .map(([key, { label, color }]) => [key, { label, color, value: 0 }]));

  if (totals.cash) totals.cash.value = Number(cashKrw) || 0;
  for (const asset of assets || []) {
    const value = Number(asset[valueKey]) || 0;
    if (value <= 0) continue;
    const category = totals[classifyAsset(asset)];
    if (category) category.value += value;
  }
  return Object.values(totals).filter(row => row.value > 0)
    .sort((a, b) => b.value - a.value);
}
