export function hasMarketRefresh(status) {
  return Object.values(status || {}).some(value => value?.refreshing);
}

export function marketStatusRows(status, now = Date.now()) {
  const labels = { prices: '시세·환율', crypto: '가상자산', dividends: '배당' };
  return Object.entries(status || {}).map(([key, value]) => {
    const time = value.updated_at ? new Date(value.updated_at).toLocaleString('ko-KR') : '확인 불가';
    const ttl = { prices: 300, crypto: 60, dividends: 86400 }[key];
    const expired = value.stale || (ttl && value.updated_at && now - Date.parse(value.updated_at) > ttl * 1000);
    const state = value.refresh_failed ? `갱신 실패 · ${value.updated_at ? '이전 데이터' : '자료 없음'}` :
      value.refreshing ? '갱신 중 · 이전 데이터' : expired ? '이전 데이터' : '캐시 기준';
    return `${labels[key] || key}: ${time} (${state})`;
  });
}
