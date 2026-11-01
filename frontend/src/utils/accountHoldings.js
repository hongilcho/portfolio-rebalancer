/** Load raw sell balances once and group only the current portfolio's accounts. */
export async function loadAccountHoldings(accounts, portfolioId, fetchHoldings) {
  if (!accounts.length) return {};
  const result = await fetchHoldings(portfolioId);
  return groupAccountHoldings(accounts, result.holdings || []);
}

export function groupAccountHoldings(accounts, holdings) {
  const grouped = Object.fromEntries(accounts.map(account => [String(account.id), []]));
  for (const holding of holdings) {
    const accountId = String(holding.account_id);
    if (Object.hasOwn(grouped, accountId)) grouped[accountId].push(holding);
  }
  return grouped;
}
