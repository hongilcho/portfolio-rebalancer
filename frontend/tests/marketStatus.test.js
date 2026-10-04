import test from 'node:test';
import assert from 'node:assert/strict';
import { hasMarketRefresh, marketStatusRows } from '../src/utils/marketStatus.js';

test('Only active background collection needs another read', () => {
  assert.equal(hasMarketRefresh({ prices: { stale: true, refreshing: true } }), true);
  assert.equal(hasMarketRefresh({ prices: { stale: true, refresh_failed: true, refreshing: false } }), false);
  assert.equal(hasMarketRefresh({ crypto: { stale: false, refreshing: false } }), false);
  assert.equal(hasMarketRefresh(undefined), false);
});

test('Old and failed snapshots are visibly distinguished from fresh cache', () => {
  const rows = marketStatusRows({
    prices: { updated_at: '2026-10-04T09:00:00Z', stale: true, refreshing: true },
    dividends: { updated_at: null, stale: true, refresh_failed: true },
    crypto: { updated_at: '2026-10-04T09:00:00Z', stale: false },
  }, Date.parse('2026-10-04T09:00:10Z'));
  assert.match(rows[0], /시세·환율.*갱신 중 · 이전 데이터/);
  assert.match(rows[1], /배당.*확인 불가.*갱신 실패 · 자료 없음/);
  assert.match(rows[2], /가상자산.*캐시 기준/);
  assert.deepEqual(marketStatusRows(undefined), []);
});

test('Restored browser snapshots use their actual age', () => {
  assert.match(marketStatusRows({prices:{updated_at:'2026-10-04T09:00:00Z',stale:false}},
    Date.parse('2026-10-04T10:00:00Z'))[0], /이전 데이터/);
});
