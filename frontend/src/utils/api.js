import {requireInvestmentProtocol} from './investmentInput';
import { authHeaders, saveAuthSession, clearAuthSession } from './authSession';

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
async function request(endpoint, options = {}, format = 'json') {
  const url = `${API_BASE_URL}${endpoint}`;
  // GET has no JSON body. Bearer authentication still requires a CORS preflight.
  const defaultHeaders = options.body ? { 'Content-Type': 'application/json' } : {};

  const authentication = endpoint === '/api/auth/verify' ? {} : authHeaders();
  const usedToken = authentication.Authorization?.slice(7);
  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
      ...authentication,
    },
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const error = new Error(errorData.detail || errorData.message || `API Error: ${response.status}`);
      error.status = response.status;
      if (response.status === 401 && usedToken) clearAuthSession(usedToken);
      throw error;
    }
    return format === 'blob' ? await response.blob() : await response.json();
  } catch (error) {
    if (error.status !== 401) console.error(`Fetch error on ${endpoint}:`, error);
    throw error;
  }
}

export const api = {
  getInvestmentCapabilities:()=>request('/api/investments/capabilities'),
  getInvestments:pid=>request(`/api/investments/${encodeURIComponent(pid)}`),
  getInvestmentPlans:pid=>request(`/api/investments/${encodeURIComponent(pid)}/plans`),
  prepareInvestment:(pid,body)=>request(`/api/investments/${encodeURIComponent(pid)}/prepare`,{method:'POST',body:JSON.stringify(body)}),
  createInvestment:(pid,body)=>request(`/api/investments/${encodeURIComponent(pid)}`,{method:'POST',body:JSON.stringify(body)}),
  getInvestment:(pid,id)=>request(`/api/investments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}`),
  setInvestmentState:(pid,id,body)=>request(`/api/investments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify(body)}),
  reviseInvestment:(pid,id,body)=>request(`/api/investments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}/goals`,{method:'PATCH',body:JSON.stringify(body)}),
  getInvestmentCandidates:(pid,id,step)=>request(`/api/investments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}/steps/${encodeURIComponent(step)}/candidates`),
  linkInvestmentRecord:(pid,id,body)=>request(`/api/investments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}/links`,{method:'POST',body:JSON.stringify(body)}),
  unlinkInvestmentRecord:(pid,id,result)=>request(`/api/investments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}/links/${encodeURIComponent(result)}`,{method:'DELETE'}),
  getBookkeepingCapabilities:()=>request('/api/trades/capabilities'),
  saveDepositEntry:(pid,body)=>request(`/api/deposit-ledger/${encodeURIComponent(pid)}`,{method:'POST',body:JSON.stringify(body)}),
  getDepositEntries:pid=>request(`/api/deposit-ledger/${encodeURIComponent(pid)}`),
  undoDepositEntry:(pid,aid,rid)=>request(`/api/deposit-ledger/${encodeURIComponent(pid)}/${encodeURIComponent(aid)}/${encodeURIComponent(rid)}`,{method:'DELETE'}),
  getLedgerCorrections: pid=>request(`/api/ledger-adjustments/${encodeURIComponent(pid)}`),
  getLedgerAccount: (pid,aid)=>request(`/api/ledger-adjustments/${encodeURIComponent(pid)}/account/${encodeURIComponent(aid)}`),
  previewLedgerCorrection: (pid,data)=>request(`/api/ledger-adjustments/${encodeURIComponent(pid)}/preview`,{method:'POST',body:JSON.stringify(data)}),
  commitLedgerCorrection: (pid,data)=>request(`/api/ledger-adjustments/${encodeURIComponent(pid)}`,{method:'POST',body:JSON.stringify(data)}),
  reviewLedgerCorrection: (pid,id)=>request(`/api/ledger-adjustments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}/review`),
  confirmLedgerHistory: (pid,id,data)=>request(`/api/ledger-adjustments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}/review`,{method:'POST',body:JSON.stringify(data)}),
  undoLedgerCorrection: (pid,id)=>request(`/api/ledger-adjustments/${encodeURIComponent(pid)}/${encodeURIComponent(id)}`,{method:'DELETE'}),
  compareNamuh: data=>request('/api/sync/namuh/compare',{method:'POST',body:JSON.stringify(data)}),

  getActivity: (pid,params) => request(`/api/activity/${encodeURIComponent(pid)}?${new URLSearchParams(params)}`),
  getNhNoticeContext: (pid,day) => request(`/api/nh-notices/${encodeURIComponent(pid)}/context?day=${encodeURIComponent(day)}`),
  commitNhNotices: async (pid,data) => {await requireInvestmentProtocol(api,data);return request(`/api/nh-notices/${encodeURIComponent(pid)}/batch`, {method:'POST',body:JSON.stringify(data)});},
  undoNhNotices: (pid,id) => request(`/api/nh-notices/${encodeURIComponent(pid)}/batch/${encodeURIComponent(id)}`, {method:'DELETE'}),
  getUsdLedgers: (portfolioId) => request(`/api/forex/?portfolio_id=${encodeURIComponent(portfolioId)}`),
  getUsdEvents: (accountId) => request(`/api/forex/${encodeURIComponent(accountId)}/events`),
  recordUsdEvent: async (accountId, event) => {await requireInvestmentProtocol(api,event);return request(`/api/forex/${encodeURIComponent(accountId)}/events`, {method:'POST',body:JSON.stringify(event)});},
  undoUsdEvent: (accountId, eventId) => request(`/api/forex/${encodeURIComponent(accountId)}/events/${encodeURIComponent(eventId)}`, {
    method: 'DELETE',
  }),
  // Auth
  verifyPassword: async (password) => {
    const result = await request('/api/auth/verify', { method: 'POST', body: JSON.stringify({ password }) });
    saveAuthSession(result);
    return result;
  },

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
  downloadBackup: () => request('/api/market/export-csv', {}, 'blob'),

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
  batchExecuteTrades: async payload=>{await requireInvestmentProtocol(api,payload);return request('/api/trades/batch',{method:'POST',body:JSON.stringify(payload)});},
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
