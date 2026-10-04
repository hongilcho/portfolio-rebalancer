import { useEffect, useRef } from 'react';
import { hasMarketRefresh } from './marketStatus';

// Poll only while an initial snapshot has an in-flight refresh. Stop on unmount,
// scope change, completion/failure, or after bounded retries (about one minute).
export function useMarketRevalidation(status, reload, scope, enabled = true) {
  const callback = useRef(reload);
  callback.current = reload;
  const attempts = useRef(0);
  const previousScope = useRef(scope);
  useEffect(() => {
    if (previousScope.current !== scope || !hasMarketRefresh(status)) attempts.current = 0;
    previousScope.current = scope;
    if (!enabled || !hasMarketRefresh(status) || attempts.current >= 15) return;
    const timer = setTimeout(() => {
      attempts.current += 1;
      callback.current();
    }, attempts.current < 5 ? 2000 : 5000);
    return () => clearTimeout(timer);
  }, [status, scope, enabled]);
}
