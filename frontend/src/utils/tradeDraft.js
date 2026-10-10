// Drafts are local input only: no broker messages or confirmed trades are stored.
export const draftKey = portfolioId => `portfolio_trade_draft_v1_${portfolioId}`;
export const hasDraftRows = rows => rows.some(r => r.assetId || Number(r.quantity) || Number(r.price));
const validDate = s => /^\d{4}-\d{2}-\d{2}$/.test(s || '') && Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0,10) === s;
// Isolate input drafts; every saved record still uses the same portfolio journal.
export function draftStorage(scope = '') {
  try {
    const storage = globalThis.localStorage;
    if (!scope) return storage;
    const prefix = `portfolio_input_${scope}/`;
    return {
      getItem: key => storage.getItem(prefix + key),
      setItem: (key, value) => storage.setItem(prefix + key, value),
      removeItem: key => storage.removeItem(prefix + key),
    };
  } catch { return undefined; }
}
const validRow = r => r && typeof r.id === 'string' && typeof r.accountId === 'string'
  && typeof r.assetId === 'string' && [r.quantity, r.price, r.exchangeRate].every(v => Number.isFinite(Number(v)) && Number(v) >= 0)
  && (!r.importSource || (r.importSource === 'NAMUH_KAKAO' && /^\d{1,10}$/.test(r.brokerOrderNo || '') && validDate(r.importDate)));
export function readTradeDraft(storage, portfolioId, now = Date.now()) {
  try {
    const raw = storage.getItem(draftKey(portfolioId));
    if (!raw) return null;
    const d = JSON.parse(raw);
    if (d.version !== 1 || d.portfolioId !== String(portfolioId) || !validDate(d.tradeDate)
      || !Number.isFinite(d.savedAt) || (!d.pendingSubmission && now - d.savedAt > 30 * 86400000) || d.savedAt > now + 60000
      || !Array.isArray(d.buyRows) || !Array.isArray(d.sellRows)
      || d.buyRows.length + d.sellRows.length > 500 || ![...d.buyRows, ...d.sellRows].every(validRow)) return null;
    if (d.pendingSubmission && (d.pendingSubmission.portfolio_id!==String(portfolioId)
      || typeof d.pendingSubmission.request_id!=='string' || !Array.isArray(d.pendingSubmission.trades))) return null;
    return hasDraftRows([...d.buyRows, ...d.sellRows]) ? d : null;
  } catch { return null; }
}
export function writeTradeDraft(storage, portfolioId, draft) {
  try {
    if (!hasDraftRows([...draft.buyRows, ...draft.sellRows])) storage.removeItem(draftKey(portfolioId));
    else storage.setItem(draftKey(portfolioId), JSON.stringify({ ...draft, version: 1, portfolioId: String(portfolioId), savedAt: Date.now() }));
    return true;
  } catch { return false; }
}
export function remainingTradeRows(buyRows, sellRows, submitted, results) {
  const succeeded = new Set((results || []).filter(r => r.success).map(r => submitted[r.index]));
  return { buyRows: buyRows.filter(r => !succeeded.has(r)), sellRows: sellRows.filter(r => !succeeded.has(r)) };
}
