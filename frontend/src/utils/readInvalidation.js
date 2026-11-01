// Price polling reads do not invalidate history. Successful ledger/master writes
// and an explicit user refresh do, including aggregate and crypto views.
export function affectsHoldingHistory(endpoint, method = 'GET') {
  const url = new URL(endpoint, 'http://local');
  if (method.toUpperCase() === 'GET') return url.searchParams.get('force_refresh') === 'true';
  if (['HEAD', 'OPTIONS'].includes(method.toUpperCase())) return false;
  if (/\/(preview|settlement-preview|compare)(\/|$)/.test(url.pathname) || /\/observe$/.test(url.pathname)) return false;
  return /^\/api\/(accounts|assets|holdings|trades|forex|nh-notices|ledger-adjustments|performance|cma|crypto|portfolios)(\/|$)/.test(url.pathname)
    || ['/api/rebalance/apply-transfers', '/api/sync/namuh'].includes(url.pathname);
}

export function affectsLedgerReads(endpoint, method = 'GET') {
  if (!affectsHoldingHistory(endpoint, method)) return false;
  const path = new URL(endpoint, 'http://local').pathname;
  // Capturing/confirming performance changes history, not positions or dollar cost.
  return !/^\/api\/performance\/[^/]+\/(snapshot|confirm|start)$/.test(path);
}
