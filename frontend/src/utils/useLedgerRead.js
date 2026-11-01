import {useEffect, useMemo, useSyncExternalStore, useCallback} from 'react';
import {api} from './api';
import {getLedgerReadStore, LEDGER_READ_MAX_AGE, normalizedReadFilters} from './ledgerReadStore';

const noSubscribe = () => () => {};
export function useLedgerRead(kind, portfolioId, {filters, active = true, initialData, client = api} = {}) {
  const filterKey = JSON.stringify(normalizedReadFilters(filters));
  const resource = useMemo(() => getLedgerReadStore(client).resource(kind, portfolioId, JSON.parse(filterKey)), [kind, portfolioId, filterKey, client]);
  const enabled = active && !initialData;
  const state = useSyncExternalStore(enabled ? resource.subscribe : noSubscribe, resource.getSnapshot, resource.getSnapshot);
  useEffect(() => {
    if (!enabled) return;
    const refresh = () => {if (document.visibilityState !== 'hidden') void resource.refresh();};
    void resource.refresh();
    const timer = setInterval(refresh, LEDGER_READ_MAX_AGE);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {clearInterval(timer);window.removeEventListener('focus', refresh);document.removeEventListener('visibilitychange', refresh);};
  }, [resource, enabled]);
  const refresh = useCallback(async (force = false) => {
    await resource.refresh({force});
    const result = resource.getSnapshot();
    if (result.stale || result.error) throw new Error(result.error || '자료 갱신을 마치지 못했습니다. 다시 조회해주세요.');
    return result.data;
  }, [resource]);
  return initialData ? {data: initialData, loading: false, stale: false, error: '', refresh} : {...state, refresh};
}
