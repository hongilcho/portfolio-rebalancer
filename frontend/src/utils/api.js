/**
 * 포트폴리오 리밸런서 프론트엔드 REST API 클라이언트 모듈
 * ========================================================
 * 백엔드 FastAPI 서버와 HTTP 통신을 수행하는 중앙 집중식 API 인터페이스입니다.
 * 
 * 주요 기능:
 * - getPortfolioBundle: 대시보드 렌더링에 필요한 모든 데이터를 1회의 요청으로 일괄 수신
 * - calculateRebalance: 리밸런싱 시뮬레이션 계산 요청
 * - applyTransfers: 리밸런싱 이체 지시서 실제 계좌 반영
 * - getPortfoliosOverview: 전체 포트폴리오 및 가상자산 통합 요약 수신
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * 공통 fetch 래퍼 함수 (JSON 직렬화 및 에러 핸들링)
 * @param {string} endpoint - API 경로
 * @param {RequestInit} [options] - fetch 옵션
 * @returns {Promise<any>} JSON 파싱된 응답 데이터
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  // GET requests have no JSON body; avoid an unnecessary CORS preflight.
  const defaultHeaders = options.body ? { 'Content-Type': 'application/json' } : {};

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
      const error = new Error(errorData.detail || errorData.message || `API Error: ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } catch (error) {
    console.error(`Fetch error on ${endpoint}:`, error);
    throw error;
  }
}

export const api = {
  getActivity: (pid,params) => request(`/api/activity/${encodeURIComponent(pid)}?${new URLSearchParams(params)}`),
  getNhNoticeContext: (pid,day) => request(`/api/nh-notices/${encodeURIComponent(pid)}/context?day=${encodeURIComponent(day)}`),
  commitNhNotices: (pid,data) => request(`/api/nh-notices/${encodeURIComponent(pid)}/batch`, {method:'POST',body:JSON.stringify(data)}),
  undoNhNotices: (pid,id) => request(`/api/nh-notices/${encodeURIComponent(pid)}/batch/${encodeURIComponent(id)}`, {method:'DELETE'}),
  getUsdLedgers: (portfolioId) => request(`/api/forex/?portfolio_id=${encodeURIComponent(portfolioId)}`),
  getUsdEvents: (accountId) => request(`/api/forex/${encodeURIComponent(accountId)}/events`),
  recordUsdEvent: (accountId, event) => request(`/api/forex/${encodeURIComponent(accountId)}/events`, {
    method: 'POST', body: JSON.stringify(event),
  }),
  undoUsdEvent: (accountId, eventId) => request(`/api/forex/${encodeURIComponent(accountId)}/events/${encodeURIComponent(eventId)}`, {
    method: 'DELETE',
  }),
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

  // Dashboard Summary & High-Speed Unified Bundle
  getDashboardSummary: (portfolioId = 'default') => request(`/api/dashboard/summary?portfolio_id=${portfolioId}`),
  getPortfolioBundle: (portfolioId = 'default', forceRefresh = false) => 
    request(`/api/dashboard/bundle?portfolio_id=${portfolioId}&force_refresh=${forceRefresh}`),

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
  getPortfoliosOverview: (includeCrypto = true, forceRefresh = false) => 
    request(`/api/portfolios/overview/summary?include_crypto=${includeCrypto}&force_refresh=${forceRefresh}`),

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
  getAllHoldings: (portfolioId) => {
    const query = portfolioId && portfolioId !== 'all'
      ? `?${new URLSearchParams({ portfolio_id: portfolioId })}` : '';
    return request(`/api/holdings/all${query}`);
  },
  saveHoldings: (data) => request('/api/holdings/save', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  // Rebalancing
  getPerformance: pid => request(`/api/performance/${encodeURIComponent(pid)}`),
  startPerformance: pid => request(`/api/performance/${encodeURIComponent(pid)}/start`, {method:'POST'}),
  capturePerformance: pid => request(`/api/performance/${encodeURIComponent(pid)}/snapshot`, {method:'POST'}),
  addPerformanceFlow: (pid,data) => request(`/api/performance/${encodeURIComponent(pid)}/flows`, {method:'POST',body:JSON.stringify(data)}),
  voidPerformanceFlow: (pid,id,voided) => request(`/api/performance/${encodeURIComponent(pid)}/flows/${id}`, {method:'PATCH',body:JSON.stringify({voided})}),
  confirmPerformanceFlows: (pid,data) => request(`/api/performance/${encodeURIComponent(pid)}/confirm`, {method:'POST',body:JSON.stringify(data)}),
  getPlans: (pid) => request(`/api/plans/${encodeURIComponent(pid)}`),
  savePlan: (pid, data) => request(`/api/plans/${encodeURIComponent(pid)}`, {method:'POST',body:JSON.stringify(data)}),
  linkPlanTrade: (pid, id, data) => request(`/api/plans/${encodeURIComponent(pid)}/${id}/links`, {method:'POST',body:JSON.stringify(data)}),
  unlinkPlanTrade: (pid, id, trade) => request(`/api/plans/${encodeURIComponent(pid)}/${id}/links/${trade}`, {method:'DELETE'}),
  archivePlan: (pid, id, archived) => request(`/api/plans/${encodeURIComponent(pid)}/${id}`, {method:'PATCH',body:JSON.stringify({archived})}),
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
  getCryptoSummary: (portfolioId = 'default', forceRefresh = false) => {
    const pid = portfolioId || 'default';
    return request(`/api/crypto/summary?portfolio_id=${encodeURIComponent(pid)}&force_refresh=${forceRefresh}`);
  },
  updateCryptoHoldings: (holdings) => request('/api/crypto/holdings', {
    method: 'PUT',
    body: JSON.stringify({ holdings }),
  }),

  // System Diagnostics & Benchmark
  getSystemBenchmark: () => request('/api/system/benchmark'),
};
