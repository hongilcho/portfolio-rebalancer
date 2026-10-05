import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { api } from './api';
import { createPerformanceStore } from './performanceStore';

export function usePortfolioPerformance(portfolioId, loadedBundle, authenticated) {
  const store = useMemo(() => createPerformanceStore(portfolioId, api), [portfolioId]);
  const enabled = authenticated && !['all', 'crypto'].includes(portfolioId)
    && loadedBundle?.portfolioId === portfolioId;
  useEffect(() => {
    store.setEnabled(enabled);
    return () => store.setEnabled(false);
  }, [store, enabled]);
  // Only a newly fetched bundle triggers capture. Tab navigation and restored
  // session caches do not issue extra reads/captures or use another scope's NAV.
  useEffect(() => { if (enabled) void store.refresh(); }, [store, enabled, loadedBundle]);
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  return { ...state, run: store.run, capture: store.capture, setNotice: store.setNotice };
}
