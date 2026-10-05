import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveUsdAccount } from '../src/utils/usdAccountSelection.js';

const oldAccount = { id: 'old', portfolio_id: 'old_portfolio', deposit_usd: 300 };
const newAccount = { id: 'new', portfolio_id: 'new_portfolio', deposit_usd: 100 };

test('portfolio switch cannot submit to the old account while its replacement is loading', () => {
  const selection = resolveUsdAccount([oldAccount], 'old', 'new_portfolio');
  assert.equal(selection.account, undefined);
  assert.deepEqual(selection.accounts, []);
});

test('a delayed refresh replaces a stale selection with the displayed account and its actual USD balance', () => {
  const selection = resolveUsdAccount([newAccount], 'old', 'new_portfolio');
  assert.equal(selection.account.id, 'new');
  assert.equal(selection.account.deposit_usd, 100);
  assert.deepEqual(selection.accounts, [newAccount]);
});

test('an explicit valid account selection is kept even when another account has more USD', () => {
  const other = { ...newAccount, id: 'other', deposit_usd: 10000 };
  assert.equal(resolveUsdAccount([oldAccount, other, newAccount], 'new', 'new_portfolio').account.id, 'new');
});
