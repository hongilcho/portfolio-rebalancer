import test from 'node:test';
import assert from 'node:assert/strict';
import { createOverviewCache } from '../src/utils/overviewCache.js';

function storage() {
  const values = new Map();
  return { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) };
}

test('crypto included/excluded results remain separate, including reload', () => {
  const saved = storage();
  const cache = createOverviewCache(saved);
  const included = { include_crypto: true, grand_total: { total_eval: 120 } };
  const excluded = { include_crypto: false, grand_total: { total_eval: 100 } };
  cache.set(true, included);
  assert.equal(cache.get(false), null);
  cache.set(false, excluded);
  assert.deepEqual(cache.get(true), included);
  assert.deepEqual(cache.get(false), excluded);
  assert.deepEqual(createOverviewCache(saved).get(false), excluded);
});

test('cache from old formulas is not restored', () => {
  const saved = storage();
  saved.setItem('portfolio_overview_cache', JSON.stringify({ include_crypto: true, grand_total: {} }));
  assert.equal(createOverviewCache(saved).get(true), null);
});

test('wrong scope and corrupt cache are rejected', () => {
  const saved = storage();
  const cache = createOverviewCache(saved);
  cache.set(false, { include_crypto: true, grand_total: {} });
  assert.equal(cache.get(false), null);
  saved.setItem('portfolio_overview_v2_false', '{');
  assert.equal(cache.get(false), null);
});

test('unavailable storage still allows a memory cache', () => {
  const unavailable = { getItem() { throw Error('blocked'); }, setItem() { throw Error('full'); } };
  const cache = createOverviewCache(unavailable);
  assert.equal(cache.get(true), null);
  const data = { include_crypto: true, grand_total: {} };
  cache.set(true, data);
  assert.equal(cache.get(true), data);
});
