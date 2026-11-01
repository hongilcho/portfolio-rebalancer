// Memory only: share one request per asset scope without persisting financial data.
export const HOLDING_HISTORY_MAX_AGE = 60_000;
export function createHoldingHistoryStore(load, { now = Date.now, maxAge = HOLDING_HISTORY_MAX_AGE } = {}) {
  const entries = new Map();
  const resource = (scope, includeCrypto = false) => {
    const key = JSON.stringify([scope, Boolean(includeCrypto)]);
    if (entries.has(key)) return entries.get(key);
    let state = { data: null, loading: false, error: '' };
    let updatedAt = 0, dirty = true, generation = 0, pending = null, queued = false;
    const listeners = new Set();
    const publish = patch => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); };
    const refresh = ({ force = false } = {}) => {
      if (pending) return pending;
      if (!force && !dirty && state.data && now() - updatedAt < maxAge) return Promise.resolve(state.data);
      const version = generation;
      dirty = false;
      publish({ loading: true, error: '' });
      const job = Promise.resolve().then(() => load(scope, Boolean(includeCrypto))).then(data => {
        if (version === generation) { updatedAt = now(); publish({ data, error: '' }); }
        return data;
      }).catch(() => {
        if (version === generation) {
          dirty = true;
          publish({ error: state.data ? '과거 기록 갱신에 실패했습니다. 이전 기록을 표시합니다.' : '과거 기록을 불러오지 못했습니다. 현재 값은 아래에 표시합니다.' });
        }
        return null;
      }).finally(() => {
        if (pending !== job) return; // Logout may already have detached this read.
        pending = null;
        if (queued && listeners.size) { queued = false; void refresh({ force: true }); }
        else { queued = false; publish({ loading: false }); }
      });
      pending = job;
      return job;
    };
    const entry = {
      getSnapshot: () => state,
      subscribe: fn => { listeners.add(fn); return () => listeners.delete(fn); },
      refresh,
      invalidate() {
        generation++; dirty = true;
        if (pending) queued = true;
        else if (listeners.size) void refresh();
      },
      clear() {
        generation++; dirty = true; queued = false; pending = null; updatedAt = 0;
        publish({ data: null, loading: false, error: '' });
      },
    };
    entries.set(key, entry);
    return entry;
  };
  return {
    resource,
    invalidate: () => entries.forEach(entry => entry.invalidate()),
    clear: () => entries.forEach(entry => entry.clear()),
  };
}

// Price polling reads do not invalidate history. Successful ledger/master writes
// and an explicit user refresh do, including aggregate and crypto views.
export function affectsHoldingHistory(endpoint, method = 'GET') {
  const url = new URL(endpoint, 'http://local');
  if (method.toUpperCase() === 'GET') return url.searchParams.get('force_refresh') === 'true';
  if (['HEAD', 'OPTIONS'].includes(method.toUpperCase())) return false;
  if (/\/(preview|settlement-preview|compare)(\/|$)/.test(url.pathname) || /\/observe$/.test(url.pathname)) return false;
  return /^\/api\/(accounts|assets|holdings|trades|forex|nh-notices|ledger-adjustments|performance|cma|crypto|portfolios)(\/|$)/.test(url.pathname)
    || ['/api/rebalance/apply-transfers', '/api/sync/namuh'].includes(url.pathname);
}
