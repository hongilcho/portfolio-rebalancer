import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyAsset, sortInvestmentAssets, assetClassBreakdown } from '../src/utils/assetClasses.js';

test('Bond ticker classification does not depend on display name', () => {
  for (const ticker of ['SGOV', 'TLT', 'IEF', 'BIL', 'SHV', 'SHY', 'BND', 'AGG', '488770', '453650', '0085P0', '476760']) {
    assert.equal(classifyAsset({ ticker, name: ticker }), 'bonds', ticker);
  }
  assert.equal(classifyAsset({ ticker: ' sgov ', name: 'Unspecified ETF' }), 'bonds');
});

test('Existing money market, bond and alternative name rules are shared', () => {
  for (const name of ['KODEX 머니마켓액티브', '단기자금 ETF', '단기채 ETF', 'KOFR ETF', 'CD금리 ETF', '미국국채', '채권 ETF', 'Treasury ETF', 'Money Market ETF', 'Fixed Income ETF']) {
    assert.equal(classifyAsset({ name }), 'bonds', name);
  }
  for (const asset of [{ ticker: 'PDBC' }, { ticker: 'M04020000' }, { name: '금99.99' }, { name: '원자재 ETF' }, { name: 'Gold ETF' }, { name: 'Commodity ETF' }]) {
    assert.equal(classifyAsset(asset), 'gold_commodities');
  }
  // The word 금 in an interest-rate product must not imply gold.
  assert.equal(classifyAsset({ name: 'CD금리 ETF' }), 'bonds');
});

test('Deposits, crypto and ordinary equities retain their categories', () => {
  for (const asset of [{ is_deposit: true, name: 'Gold deposit' }, { asset_type: ' deposit ' }, { ticker: 'DEP-1' }, { name: '정기예금' }, { name: '적금' }, { name: '새마을 금융상품' }, { name: '금고 상품' }]) {
    assert.equal(classifyAsset(asset), 'deposits');
  }
  assert.equal(classifyAsset({ asset_type: 'crypto', name: 'Bitcoin Gold' }), 'crypto');
  assert.equal(classifyAsset({ market: ' CRYPTO ', ticker: 'BTC' }), 'crypto');
  assert.equal(classifyAsset({ ticker: 'VT', name: '세계주식 ETF' }), 'equity');
  assert.equal(classifyAsset(undefined), 'equity');
});

test('Investment order is asset class first, KRW value descending within each class', () => {
  const assets = [
    { ticker: 'DEP-1', eval_amount: 1000 },
    { ticker: 'PDBC', eval_amount: 900 },
    { ticker: 'SGOV', eval_amount: 800 },
    { ticker: 'VT', eval_amount: '100' },
    { ticker: '488770', eval_amount: 700 },
    { ticker: 'QQQ', eval_amount: 200 },
  ];
  const original = structuredClone(assets);
  assert.deepEqual(sortInvestmentAssets(assets).map(asset => asset.ticker),
    ['QQQ', 'VT', 'SGOV', '488770', 'PDBC', 'DEP-1']);
  assert.deepEqual(assets, original);
});

test('Individual and overview charts have identical financial asset categories and totals', () => {
  const assets = [
    { ticker: 'VT', eval_amount: 100 },
    { ticker: 'SGOV', eval_amount: 200 },
    { ticker: 'TLT', eval_amount: 300 },
    { ticker: '488770', eval_amount: 400 },
    { ticker: 'M04020000', eval_amount: 500 },
    { is_deposit: true, eval_amount: 600 },
    { ticker: 'QQQ', eval_amount: 0 },
  ];
  const overview = assets.map(({ eval_amount, ...asset }) => ({ ...asset, total_eval_amount: eval_amount }));
  const individualRows = assetClassBreakdown(assets, 'eval_amount');
  const overviewRows = assetClassBreakdown(overview, 'total_eval_amount', { includeCrypto: true, cashKrw: 0 });
  assert.deepEqual(overviewRows, individualRows);
  assert.deepEqual(Object.fromEntries(individualRows.map(row => [row.label, row.value])),
    { '📜 채권': 900, '🏦 예금': 600, '🥇 대체투자': 500, '📈 주식': 100 });
  assert.equal(individualRows.reduce((sum, row) => sum + row.value, 0), 2100);
});

test('Overview preserves crypto and cash once; deposit-excluded data stays excluded', () => {
  const assets = [{ ticker: 'VT', total_eval_amount: 100 }, { market: 'CRYPTO', total_eval_amount: 200 }];
  const rows = assetClassBreakdown(assets, 'total_eval_amount', { includeCrypto: true, cashKrw: 300 });
  assert.equal(rows.reduce((sum, row) => sum + row.value, 0), 600);
  assert.deepEqual(assetClassBreakdown(assets, 'total_eval_amount'),
    [{ label: '📈 주식', color: '#3B82F6', value: 100 }]);
  assert.deepEqual(assetClassBreakdown([], 'eval_amount'), []);
  assert.equal(assetClassBreakdown(assets, 'total_eval_amount', { cashKrw: 300 })[0].value, 300);
});
