import {createReadStore} from './readStore.js';

export const LEDGER_READ_MAX_AGE = 60_000;
const stores = new WeakMap();
export function normalizedReadFilters(filters = {}) {
  return Object.fromEntries(Object.entries(filters).filter(([,v]) => v !== '' && v != null).sort(([a],[b]) => a.localeCompare(b)));
}
export function createLedgerReadStore(client, options = {}) {
  const store = createReadStore((kind, portfolioId, filters) => {
    if (kind === 'realized') return client.getRealizedGains(portfolioId, filters);
    if (kind === 'usd') return client.getUsdLedgers(portfolioId);
    if (kind === 'holdings') return client.getAllHoldings(portfolioId);
    throw new Error('지원하지 않는 조회입니다.');
  }, {maxAge: LEDGER_READ_MAX_AGE, errorMessage: error => error?.message || '자료를 불러오지 못했습니다.', ...options});
  return {...store, resource: (kind, portfolioId, filters) => store.resource(kind, String(portfolioId), normalizedReadFilters(filters))};
}
export function getLedgerReadStore(client) {
  if (!stores.has(client)) stores.set(client, createLedgerReadStore(client));
  return stores.get(client);
}
