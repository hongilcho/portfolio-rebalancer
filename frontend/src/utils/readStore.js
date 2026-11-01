// Shared, memory-only reads. Each key owns one request and its invalidation generation.
export function createReadStore(load, { now = Date.now, maxAge = 60_000, errorMessage = () => '자료를 불러오지 못했습니다.' } = {}) {
  const entries = new Map();
  const resource = (...args) => {
    const key = JSON.stringify(args);
    if (entries.has(key)) return entries.get(key);
    let state = { data: null, loading: false, error: '', stale: true };
    let updatedAt = 0, dirty = true, generation = 0, pending = null, queued = false;
    const listeners = new Set();
    const publish = patch => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); };
    const refresh = ({ force = false } = {}) => {
      if (pending) return pending;
      if (!force && !dirty && state.data && now() - updatedAt < maxAge) return Promise.resolve(state.data);
      const version = generation;
      dirty = false;
      publish({ loading: true, error: '', stale: true });
      const job = Promise.resolve().then(() => load(...args)).then(data => {
        if (version === generation) { updatedAt = now(); publish({ data, error: '', stale: false }); }
        return null;
      }).catch(error => {
        if (version === generation) {
          dirty = true;
          publish({ error: errorMessage(error, state.data) });
        }
        return null;
      }).then(() => {
        if (pending !== job) return; // Logout may already have detached this read.
        pending = null;
        if (queued && listeners.size) { queued = false; return refresh({ force: true }); }
        queued = false; publish({ loading: false });
        return state.stale ? null : state.data;
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
        publish({ stale: true });
        if (pending) queued = true;
        else if (listeners.size) void refresh();
      },
      clear() {
        generation++; dirty = true; queued = false; pending = null; updatedAt = 0;
        publish({ data: null, loading: false, error: '', stale: true });
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

