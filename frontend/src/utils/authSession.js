const KEY = 'portfolio_api_session_v1';
let memorySession = null;
let listeners = new Set();

function storage() { try { return globalThis.sessionStorage; } catch { return null; } }
export function getAuthSession() {
  let value = memorySession;
  if (!value) { try { value = JSON.parse(storage()?.getItem(KEY) || 'null'); } catch {} }
  if (!value || typeof value.access_token !== 'string' || !Number.isFinite(value.expires_at)
      || value.expires_at * 1000 <= Date.now()) return null;
  memorySession = value;
  return value;
}
export function saveAuthSession(value) {
  if (!value || typeof value.access_token !== 'string' || !value.access_token
      || !Number.isFinite(value.expires_at) || value.expires_at * 1000 <= Date.now()) {
    throw new Error('서버 인증 응답이 올바르지 않습니다. 백엔드 배포 상태를 확인해주세요.');
  }
  memorySession = { access_token: value.access_token, expires_at: value.expires_at };
  try { storage()?.setItem(KEY, JSON.stringify(memorySession)); } catch { /* memory remains usable */ }
  try { globalThis.localStorage?.removeItem('portfolio_auth'); } catch {}
}
export function clearAuthSession(expectedToken) {
  let current = memorySession;
  if (!current) { try { current = JSON.parse(storage()?.getItem(KEY) || 'null'); } catch {} }
  if (expectedToken && current?.access_token !== expectedToken) return;
  const hadSession = Boolean(current);
  memorySession = null;
  try { storage()?.removeItem(KEY); } catch {}
  try {
    const store = storage();
    for (let i = (store?.length || 0) - 1; i >= 0; i--) {
      const key = store.key(i);
      if (key?.startsWith('portfolio_dashboard_v2_') || key?.startsWith('portfolio_overview_v2_')) store.removeItem(key);
    }
  } catch {}
  if (hadSession) for (const listener of listeners) listener();
}
export function onAuthExpired(listener) {
  listeners.add(listener);
  // Expiry may occur between initial render and effect subscription.
  if (!getAuthSession()) listener();
  return () => listeners.delete(listener);
}
export function authHeaders() {
  const session = getAuthSession();
  if (!session) { clearAuthSession(); throw Object.assign(new Error('다시 로그인해주세요.'), { status: 401 }); }
  return { Authorization: `Bearer ${session.access_token}` };
}
