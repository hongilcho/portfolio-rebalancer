// Presentation only. Posting and correction validation stay in the existing APIs.
export const cmaMoney = value => value == null || (typeof value==='string' && value.trim()==='') || !Number.isFinite(Number(value)) ? null : Number(value);
export function cmaBalanceReview(account, observation, preview) {
  const book = cmaMoney(preview?.book_krw) ?? cmaMoney(account?.deposit_krw);
  const returned = observation?.state === 'CASH_RETURNED';
  const principal = observation?.state === 'CMA_PRINCIPAL_VERIFIED';
  // Withdrawal availability and an unverified zero are never correction targets.
  const target = returned ? (cmaMoney(preview?.broker_krw) ?? cmaMoney(observation.total_krw))
    : principal ? cmaMoney(observation.posted_krw) : null;
  const observed = target ?? cmaMoney(observation?.total_krw);
  const delta = book != null && target != null ? target - book : null;
  const interestReady = Boolean(preview && preview.can_apply !== false && cmaMoney(preview.interest_krw) > 0);
  if (interestReady) return {book, observed, target, delta, tone:'ready', title:'확인된 이자를 반영할 수 있습니다.',
    description:'지급 명세로 확인한 금액만 장부에 추가합니다.', interestReady};
  if (delta === 0) return {book, observed, target, delta, tone:'matched', title:'앱 잔고와 조회 잔고가 같습니다.',
    description:'추가로 잔고를 정정할 필요가 없습니다.', interestReady};
  if (delta != null) return {book, observed, target, delta, tone:'review', title:'앱과 실제 조회 잔고에 차이가 있습니다.',
    description:'누락된 입출금·이체를 먼저 확인하세요. 남은 차이는 이자로 단정하지 않고 정정할 수 있습니다.', interestReady};
  if (observation) return {book, observed, target, delta, tone:'review', title:observation.state==='ZERO_UNVERIFIED' ? '조회값은 0원입니다. 실제 잔고를 확인해 주세요.' : '잔고를 바로 맞추기 전에 확인이 필요합니다.',
    description:observation.state==='ZERO_UNVERIFIED' ? '전액 이체했다면 이체 기록부터 확인하세요. 이 조회값만으로 앱 잔고를 0원으로 바꾸지 않습니다.' : 'CMA 상품 잔고나 지급 기준이 아직 확인되지 않았습니다. MTS에서 확인한 잔고로 정정할 수 있습니다.', interestReady};
  return {book, observed:null, target:null, delta:null, tone:'idle', title:'실제 잔고를 확인해 보세요.',
    description:'조회만으로 장부가 바뀌지 않습니다. 확인 결과에 따라 다음 조치를 안내합니다.', interestReady};
}
