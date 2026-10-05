import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

const noop = () => {};
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
  cacheDir: 'node_modules/.vite-test-usd-form',
  logLevel: 'error', server: { middlewareMode: true, watch: null, hmr: false, ws: false } });
const { default: TradeBatchForm } = await server.ssrLoadModule('/src/components/Tab4History/TradeBatchForm.jsx');
const props = {
  tradeDate: '2026-01-02', setTradeDate: noop,
  accounts: [{ id: 'acc', account_alias: 'USD account', account_type: 'GENERAL' }],
  assets: [{ id: 'vt', name: 'VT', market: 'US', allowed_accounts: ['acc'] }],
  buyRows: [{ id: 'b', accountId: 'acc', assetId: 'vt', quantity: 5, price: 100, exchangeRate: 9999 }],
  sellRows: [{ id: 's', accountId: 'acc', assetId: 'vt', quantity: 1, price: 120, exchangeRate: 1500 }],
  accountHoldingsMap: { acc: [{ asset_id: 'vt', quantity: 10 }] },
  updateBuyRow: noop, updateSellRow: noop, removeBuyRow: noop, removeSellRow: noop,
  addBuyRow: noop, addSellRow: noop, handleSaveBatchTrades: noop, usdKrw: 1400,
};

try {
  test('tracked buy displays locked funding average, while sell asks for receipt valuation', () => {
    const markup = renderToStaticMarkup(React.createElement(TradeBatchForm, { ...props,
      usdLedgers: [{ account_id: 'acc', average_rate: 1360, usd_balance: 1000 }] }));
    assert.match(markup, /달러 평균 취득환율/);
    assert.match(markup, /readOnly=""[^>]*value="1360"/);
    assert.match(markup, /680,000 원/);
    assert.doesNotMatch(markup, /value="9999"/);
    assert.match(markup, /매도대금 수취기준환율/);
    assert.match(markup, /실제 환전이 발생한 기록은 아닙니다/);
    assert.match(markup, /value="1500"/);
  });

  test('untracked accounts retain manual exchange rate input', () => {
    const markup = renderToStaticMarkup(React.createElement(TradeBatchForm, props));
    assert.match(markup, /체결환율/);
    assert.match(markup, /value="9999"/);
    assert.doesNotMatch(markup, /readOnly=""/);
  });

  test('saving freezes batch fields to prevent editing a request being committed', () => {
    const markup = renderToStaticMarkup(React.createElement(TradeBatchForm, { ...props, savingBatch: true }));
    assert.match(markup, /trade-forms-grid" inert=""/);
    assert.match(markup, /type="date"[^>]*disabled=""/);
  });
} finally {
  await server.close();
}
