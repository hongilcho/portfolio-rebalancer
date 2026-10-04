// Compare complete rendered markup before/after splitting the presentation UI.
// Hooks are seeded only in this SSR transform to exercise loaded views/forms.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { parseSync } from 'rolldown/experimental';

const root = fileURLToPath(new URL('../', import.meta.url));
const fixture = JSON.parse(await readFile(new URL('./fixtures/uiPresentation.json', import.meta.url), 'utf8'));
const baselineUrl = new URL('./fixtures/uiPresentationBeforeSplit.json', import.meta.url);
// Captured from b273a8a before extracting any JSX; never regenerate as part
// of the test run, so accidental UI changes cannot bless their own output.
const baseline = JSON.parse(await readFile(baselineUrl, 'utf8'));
const noop = () => {};
const realDate = globalThis.Date;
class FixedDate extends realDate {
  constructor(...args) { super(...(args.length ? args : ['2026-10-05T00:00:00Z'])); }
  static now() { return realDate.parse('2026-10-05T00:00:00Z'); }
}
globalThis.Date = FixedDate;
const memoryStorage = { getItem: () => null, setItem: noop };
const realLocalStorage = globalThis.localStorage;
const realSessionStorage = globalThis.sessionStorage;
globalThis.localStorage = memoryStorage;
globalThis.sessionStorage = memoryStorage;
const realFetch = globalThis.fetch;
globalThis.fetch = () => { throw new Error('Presentation SSR must not request an API'); };

const modules = {
  dashboard: '/src/components/Tab1Dashboard/DashboardTab.jsx',
  settings: '/src/components/Tab5Settings/SettingsTab.jsx',
  history: '/src/components/Tab4History/HistoryTab.jsx',
  overview: '/src/components/Portfolios/AllPortfoliosOverview.jsx',
  crypto: '/src/components/Tab5Crypto/CryptoTab.jsx',
};
const stateNames = {
  DashboardTab: ['includeDeposits', 'expandedAccs'],
  SettingsTab: ['isAddAccOpen', 'editAccTarget', 'accForm', 'isAddAssetOpen', 'editAssetTarget', 'assetForm'],
  HistoryTab: ['buyRows', 'sellRows', 'accountHoldingsMap', 'trades', 'selectedTradeIds'],
  AllPortfoliosOverview: ['data', 'loading', 'includeCrypto'],
  CryptoTab: ['data', 'loading'],
};
const server = await createServer({ root, logLevel: 'error',
  server: { middlewareMode: true, watch: null, hmr: false },
  plugins: [{ name: 'synthetic-presentation-state', enforce: 'pre',
    transform(source, id, options) {
      if (!options?.ssr) return;
      const name = path.basename(id, '.jsx');
      if (!stateNames[name]) return;
      const { program, errors } = parseSync(id, source);
      assert.equal(errors.length, 0);
      const edits = [];
      const walk = (node) => {
        if (!node || typeof node !== 'object') return;
        if (node.type === 'VariableDeclarator' && node.id.type === 'ArrayPattern'
            && node.init?.callee?.name === 'useState') {
          const state = node.id.elements[0]?.name;
          if (stateNames[name].includes(state)) {
            const arg = node.init.arguments[0];
            edits.push({ start: arg.start, end: arg.end,
              text: `(Object.hasOwn(globalThis.__presentationState, '${state}') ? globalThis.__presentationState.${state} : (${source.slice(arg.start, arg.end)}))` });
          }
        }
        for (const value of Object.values(node)) {
          if (Array.isArray(value)) value.forEach(walk);
          else if (value && typeof value === 'object') walk(value);
        }
      };
      walk(program);
      for (const edit of edits.sort((a, b) => b.start-a.start)) {
        source = source.slice(0, edit.start) + edit.text + source.slice(edit.end);
      }
      return source;
    },
  }],
});

const base = {
  assets: fixture.bundle.assets, accounts: fixture.bundle.accounts,
  pricesData: fixture.bundle.prices_data, onSaved: noop, currentPortfolioId: 'default',
};
const accountForm = { ...base.accounts[0], is_unlimited: false, notes: '', limit_preference: 'ANNUAL' };
const assetForm = { ...base.assets[1], is_gold: false, is_deposit: false, account_id: '',
  account_no: '', deposit_principal: 10000000, interest_rate: 4, start_date: '2026-10-05',
  maturity_date: '2027-10-05', early_termination_rate: 0.5, tax_rate: 15.4, lock_rebalance_sell: true };
const deposit = { ...assetForm, ...base.assets.find(a => a.is_deposit) };
const holdingMap = Object.fromEntries(base.accounts.map(a => [a.id, fixture.holdings.filter(h => h.account_id === a.id)]));
const rows = [{ id: '1', accountId: base.accounts[0].id, assetId: base.assets[1].id,
  quantity: 1.25, price: 100, exchangeRate: 1400 },
{ id: '2', accountId: base.accounts[1].id, assetId: base.assets[0].id,
  quantity: 2, price: 100000, exchangeRate: 1 }];
const cases = [
  ['dashboard/KRW', 'dashboard', { ...base, dashboardData: fixture.bundle.dashboard, onRefresh: noop }],
  ['dashboard/USD', 'dashboard', { ...base, dashboardData: fixture.bundle.dashboard, onRefresh: noop, currencyMode: 'USD' }],
  ['dashboard/no-deposit', 'dashboard', { ...base, dashboardData: fixture.bundle.dashboard, onRefresh: noop }, { includeDeposits: false }],
  ['dashboard/collapsed', 'dashboard', { ...base, dashboardData: fixture.bundle.dashboard, onRefresh: noop }, { expandedAccs: Object.fromEntries(base.accounts.map(a => [a.id, false])) }],
  ['dashboard/no-data', 'dashboard', { ...base, dashboardData: null }],
  ['settings/tables', 'settings', base],
  ['settings/new-account', 'settings', base, { isAddAccOpen: true, accForm: accountForm }],
  ['settings/edit-account', 'settings', base, { editAccTarget: base.accounts[0], accForm: accountForm }],
  ['settings/new-US-asset', 'settings', base, { isAddAssetOpen: true, assetForm }],
  ['settings/edit-deposit', 'settings', base, { editAssetTarget: deposit, assetForm: deposit }],
  ['history/empty', 'history', { ...base, priceMap: fixture.bundle.prices_data.price_map, usdKrw: 1400 }],
  ['history/filled-forms', 'history', { ...base, priceMap: fixture.bundle.prices_data.price_map, usdKrw: 1400 },
    { buyRows: rows, sellRows: [rows[0]], accountHoldingsMap: holdingMap, trades: fixture.trades, selectedTradeIds: [fixture.trades[0].id] }],
  ['overview/KRW', 'overview', { onSelectPortfolio: noop }, { data: fixture.overview, loading: false }],
  ['overview/USD', 'overview', { onSelectPortfolio: noop, currencyMode: 'USD' }, { data: fixture.overview, loading: false }],
  ['overview/no-crypto', 'overview', { onSelectPortfolio: noop }, { data: fixture.overviewNoCrypto, loading: false, includeCrypto: false }],
  ['crypto/loaded', 'crypto', {}, { data: fixture.crypto, loading: false }],
  ['crypto/empty', 'crypto', {}, { data: {}, loading: false }],
];

try {
  const loaded = Object.fromEntries(await Promise.all(Object.entries(modules).map(async ([key, file]) =>
    [key, (await server.ssrLoadModule(file)).default])));
  for (const [name, module, props, states = {}] of cases) {
    await test(`presentation stays identical: ${name}`, () => {
      globalThis.__presentationState = states;
      const markup = renderToStaticMarkup(React.createElement(loaded[module], props));
      const hash = createHash('sha256').update(markup).digest('hex');
      assert.equal(hash, baseline.sha256[name], `${name} markup changed`);
    });
  }
} finally {
  await server.close();
  globalThis.Date = realDate;
  globalThis.fetch = realFetch;
  if (realLocalStorage === undefined) delete globalThis.localStorage;
  else globalThis.localStorage = realLocalStorage;
  if (realSessionStorage === undefined) delete globalThis.sessionStorage;
  else globalThis.sessionStorage = realSessionStorage;
  delete globalThis.__presentationState;
}
