// Shared by tabs 4 and 6. A store belongs to one portfolio and serializes
// background captures with user changes, so older reads cannot replace newer ones.
export function createPerformanceStore(portfolioId, client) {
  let state = { data: null, busy: false, error: '', notice: '' };
  let enabled = false;
  let pending = 0;
  let queue = Promise.resolve();
  const listeners = new Set();
  const update = patch => {
    if (!enabled) return;
    state = { ...state, ...patch };
    listeners.forEach(listener => listener());
  };
  const read = async () => {
    const data = await client.getPerformance(portfolioId);
    update({ data });
    return data;
  };
  const capture = async () => {
    if (!enabled) return;
    const result = await client.capturePerformance(portfolioId);
    update({ notice: result.saved ? '오늘의 최신 조회 평가액을 저장했습니다.' : result.message });
  };
  const enqueue = action => {
    pending++;
    update({ busy: true });
    const job = queue.then(async () => {
      try {
        if (!enabled) return false;
        update({ error: '', notice: '' });
        await action();
        return enabled;
      } catch (error) {
        update({ error: error.message });
        return false;
      } finally {
        pending--;
        update({ busy: pending > 0 });
      }
    });
    queue = job;
    return job;
  };
  return {
    getSnapshot: () => state,
    subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); },
    setEnabled: value => { enabled = value; },
    refresh: () => enqueue(async () => {
      const data = await read();
      if (enabled && data.tracking) {
        await capture();
        if (enabled) await read();
      }
    }),
    run: action => enqueue(async () => {
      // Even a rejected change may mean another client has changed the record.
      try { await action(); }
      finally { if (enabled) await read(); }
    }),
    capture,
    setNotice: notice => update({ notice }),
  };
}
