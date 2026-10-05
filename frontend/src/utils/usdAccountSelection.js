/** Keep a delayed account refresh from selecting another portfolio's account. */
export function resolveUsdAccount(accounts, selectedId, portfolioId) {
  const scoped = portfolioId && portfolioId !== 'all'
    ? accounts.filter(account => String(account.portfolio_id) === String(portfolioId))
    : accounts;
  const account = scoped.find(a => String(a.id) === String(selectedId))
    || scoped.find(a => Number(a.deposit_usd) > 0) || scoped[0];
  return { accounts: scoped, account };
}
