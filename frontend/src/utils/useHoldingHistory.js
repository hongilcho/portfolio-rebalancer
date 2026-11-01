import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { holdingHistoryStore } from './api';
import { HOLDING_HISTORY_MAX_AGE } from './holdingHistoryStore';

const noSubscribe = () => () => {};

export function useHoldingHistory(scope, includeCrypto, initialData) {
  const resource = useMemo(() => holdingHistoryStore.resource(scope, includeCrypto), [scope, includeCrypto]);
  const state = useSyncExternalStore(initialData ? noSubscribe : resource.subscribe, resource.getSnapshot, resource.getSnapshot);
  useEffect(() => {
    if (initialData) return;
    const refresh = () => { if (document.visibilityState !== 'hidden') void resource.refresh(); };
    void resource.refresh();
    const timer = setInterval(refresh, HOLDING_HISTORY_MAX_AGE);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [resource, initialData]);
  return initialData ? { data: initialData, loading: false, error: '' } : state;
}
