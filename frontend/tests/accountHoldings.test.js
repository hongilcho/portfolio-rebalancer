import test from 'node:test';
import assert from 'node:assert/strict';
import { loadAccountHoldings } from '../src/utils/accountHoldings.js';

test('loads multiple accounts with one request and keeps raw fractional balances', async () => {
  const accounts = Array.from({ length: 8 }, (_, id) => ({ id }));
  const holdings = [
    { account_id: '0', asset_id: 'us', quantity: 1.25, avg_price: 140000 },
    { account_id: 7, asset_id: 'kr', quantity: 3, avg_price: 80000 },
    { account_id: 7, asset_id: 'closed', quantity: 0 },
    { account_id: 'another-portfolio', asset_id: 'secret', quantity: 9 },
  ];
  const requests = [];
  const grouped = await loadAccountHoldings(accounts, 'selected', async (pid) => {
    requests.push(pid);
    return { holdings };
  });
  assert.deepEqual(requests, ['selected']);
  assert.deepEqual(grouped['0'], [holdings[0]]);
  assert.deepEqual(grouped['7'], holdings.slice(1, 3));
  assert.deepEqual(grouped['1'], []);
  assert.equal(Object.hasOwn(grouped, 'another-portfolio'), false);
  assert.equal(holdings[0].quantity, 1.25);
});

test('empty portfolios do not request holdings', async () => {
  const result = await loadAccountHoldings([], 'empty', () => {
    assert.fail('No request expected');
  });
  assert.deepEqual(result, {});
});

test('a refreshed response replaces sold balances instead of merging stale ones', async () => {
  const accounts = [{ id: 'a' }];
  const first = await loadAccountHoldings(accounts, 'p', async () => ({
    holdings: [{ account_id: 'a', asset_id: 'sold', quantity: 10 }],
  }));
  const refreshed = await loadAccountHoldings(accounts, 'p', async () => ({ holdings: [] }));
  assert.equal(first.a.length, 1);
  assert.deepEqual(refreshed, { a: [] });
});

test('failed balances are surfaced to the caller', async () => {
  await assert.rejects(loadAccountHoldings([{ id: 'a' }], 'p', async () => {
    throw new Error('Unavailable');
  }), /Unavailable/);
});
