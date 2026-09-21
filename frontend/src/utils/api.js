const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const defaultHeaders = {
    'Content-Type': 'application/json',
  };

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || errorData.message || `API Error: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Fetch error on ${endpoint}:`, error);
    throw error;
  }
}

export const api = {
  // Auth
  verifyPassword: (password) => request('/api/auth/verify', {
    method: 'POST',
    body: JSON.stringify({ password }),
  }),

  // Market & Exchange Rate
  getExchangeRate: () => request('/api/market/exchange-rate'),
  overrideExchangeRate: (usd_krw) => request('/api/market/exchange-rate/override', {
    method: 'POST',
    body: JSON.stringify({ usd_krw }),
  }),
  refreshExchangeRate: () => request('/api/market/exchange-rate/refresh', {
    method: 'POST',
  }),
  getPrices: (forceRefresh = false, portfolioId = null) => {
    let url = `/api/market/prices?force_refresh=${forceRefresh}`;
    if (portfolioId && portfolioId !== 'all') {
      url += `&portfolio_id=${portfolioId}`;
    }
    return request(url);
  },
  getExportCsvUrl: () => `${API_BASE_URL}/api/market/export-csv`,

  // Dashboard Summary
  getDashboardSummary: (portfolioId = 'default') => request(`/api/dashboard/summary?portfolio_id=${portfolioId}`),

  // Portfolios Management & Overview
  getPortfolios: () => request('/api/portfolios/'),
  createPortfolio: (name, description = '') => request('/api/portfolios/', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  }),
  updatePortfolio: (id, name, description = '') => request(`/api/portfolios/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ name, description }),
  }),
  deletePortfolio: (id) => request(`/api/portfolios/${id}`, {
    method: 'DELETE',
  }),
  getPortfoliosOverview: (includeCrypto = true) => request(`/api/portfolios/overview/summary?include_crypto=${includeCrypto}`),

  // Accounts
  getAccounts: (portfolioId) => request(`/api/accounts/${portfolioId ? `?portfolio_id=${portfolioId}` : ''}`),
  createAccount: (data) => request('/api/accounts/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updateAccount: (id, data) => request(`/api/accounts/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  deleteAccount: (id) => request(`/api/accounts/${id}`, {
    method: 'DELETE',
  }),
  updatePriorities: (priority_map) => request('/api/accounts/priorities/batch', {
    method: 'PUT',
    body: JSON.stringify({ priority_map }),
  }),
  toggleLimitExhausted: (id, is_exhausted) => request(`/api/accounts/${id}/toggle-exhaust`, {
    method: 'PUT',
    body: JSON.stringify({ is_exhausted }),
  }),

  // Assets
  getAssets: (portfolioId) => request(`/api/assets/${portfolioId ? `?portfolio_id=${portfolioId}` : ''}`),
  createAsset: (data) => request('/api/assets/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updateAsset: (id, data) => request(`/api/assets/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  toggleAssetActive: (id, is_active) => request(`/api/assets/${id}/active`, {
    method: 'POST',
    body: JSON.stringify({ is_active }),
  }),
  deleteAsset: (id) => request(`/api/assets/${id}`, {
    method: 'DELETE',
  }),
  batchUpdateWeights: (items) => request('/api/assets/weights/batch', {
    method: 'PUT',
    body: JSON.stringify({ items }),
  }),

  // Holdings
  getAccountHoldings: (accountId) => request(`/api/holdings/account/${accountId}`),
  saveHoldings: (data) => request('/api/holdings/save', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  // Rebalancing
  calculateRebalance: (data) => request('/api/rebalance/calculate', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  applyTransfers: (transfer_plan) => request('/api/rebalance/apply-transfers', {
    method: 'POST',
    body: JSON.stringify({ transfer_plan }),
  }),

  // Trades
  getTrades: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/api/trades/${query ? `?${query}` : ''}`);
  },
  batchExecuteTrades: (trade_date, trades) => request('/api/trades/batch', {
    method: 'POST',
    body: JSON.stringify({ trade_date, trades }),
  }),
  batchDeleteTrades: (trade_ids) => request('/api/trades/batch', {
    method: 'DELETE',
    body: JSON.stringify({ trade_ids }),
  }),

  // Sync
  syncNamuh: () => request('/api/sync/namuh', {
    method: 'POST',
  }),

  // Crypto (Bitcoin & Ethereum)
  getCryptoSummary: (portfolioId = 'default') => {
    const pid = portfolioId || 'default';
    return request(`/api/crypto/summary?portfolio_id=${encodeURIComponent(pid)}`);
  },
  updateCryptoHoldings: (holdings) => request('/api/crypto/holdings', {
    method: 'PUT',
    body: JSON.stringify({ holdings }),
  }),
};
