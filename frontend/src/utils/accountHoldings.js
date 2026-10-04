/** Load raw sell balances once and group only the current portfolio's accounts. */
export async function loadAccountHoldings(accounts, portfolioId, fetchHoldings) {
  const grouped = Object.fromEntries(accounts.map((account) => [String(account.id), []]));
  if (!accounts.length) return grouped;

  const result = await fetchHoldings(portfolioId);
  for (const holding of result.holdings || []) {
    const accountId = String(holding.account_id);
    if (Object.hasOwn(grouped, accountId)) grouped[accountId].push(holding);
  }
  return grouped;
}
