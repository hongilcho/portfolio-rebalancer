// Keep the exact request until its result is known, including across navigation.
export const readPendingRequest = (key, storage) => {
  try { storage=storage || globalThis.localStorage; const row = JSON.parse(storage.getItem(key));
    return row && typeof row.payload?.request_id === 'string' && row.payload.request_id.length >= 8 ? row : null;
  } catch { return null; }
};
export function persistPendingRequest(key, row, storage) {
  try { storage=storage || globalThis.localStorage; storage.setItem(key,JSON.stringify(row)); }
  catch { throw new Error('저장 결과 확인을 위한 임시 저장을 사용할 수 없습니다. 브라우저 저장소를 허용한 뒤 다시 시도해주세요.'); }
}
export function clearPendingRequest(key, storage) {
  try { storage=storage || globalThis.localStorage; storage.removeItem(key); } catch { /* An old exact request can safely retry. */ }
}

export async function requireBookkeepingProtocol(client) {
  try { const result=await client.getBookkeepingCapabilities();
    if(result.bookkeeping_protocol===1)return;
  }catch { /* A pre-upgrade backend cannot promise idempotent manual writes. */ }
  throw new Error('백엔드의 새 장부 처리 버전이 필요합니다. Render 배포와 새로고침 후 다시 입력해주세요. 요청은 보내지 않았습니다.');
}

export async function singleSubmission(lock,action) {
  if(lock.current)return;
  lock.current=true;
  try{return await action();}finally{lock.current=false;}
}
