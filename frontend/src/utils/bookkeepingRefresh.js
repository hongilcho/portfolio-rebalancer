// Every view gets a refresh attempt even when another read fails.
export async function refreshBookkeeping(reads) {
  const entries = Object.entries(reads).filter(([,read]) => typeof read === 'function');
  const results = await Promise.allSettled(entries.map(([,read]) => Promise.resolve().then(read)));
  const failed = results.flatMap((result,i) => result.status === 'rejected' ? [entries[i][0]] : []);
  if (failed.length) throw new Error(`화면 갱신 실패: ${failed.join(', ')}. 장부를 다시 입력하지 말고 새로고침해주세요.`);
}
