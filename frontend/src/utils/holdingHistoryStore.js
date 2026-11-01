import {createReadStore} from './readStore.js';
// Memory only: share one request per asset scope without persisting financial data.
export const HOLDING_HISTORY_MAX_AGE = 60_000;
export function createHoldingHistoryStore(load, options = {}) {
  const store = createReadStore(load, {
    maxAge: HOLDING_HISTORY_MAX_AGE,
    errorMessage: (_error, data) => data ? '과거 기록 갱신에 실패했습니다. 이전 기록을 표시합니다.' : '과거 기록을 불러오지 못했습니다. 현재 값은 아래에 표시합니다.',
    ...options,
  });
  return {...store, resource: (scope, includeCrypto = false) => store.resource(scope, Boolean(includeCrypto))};
}

export {affectsHoldingHistory} from './readInvalidation.js';
