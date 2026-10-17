export const cmaStateLabel = state => ({
  UNVERIFIED:'조회 기준 확인 필요', SETTLEMENT_UNVERIFIED:'예수금 기준이 달라 확인 필요',
  OTHER_ASSETS_UNVERIFIED:'다른 보유자산 확인 필요', NIGHT_TRANSITION:'야간 전환 중 · 장부 유지',
  AWAITING_CASH_RETURN:'CMA 상품에서 현금 반환 대기', ZERO_UNVERIFIED:'0원 잔고 · 반환 확인 대기',
  CASH_RETURNED:'현금 잔고 확인', AWAITING_STABLE_RETURN:'두 번째 현금 잔고 확인 대기',
  REVIEW_INTEREST:'이자 반영 검토', AUTO_LIMIT_REVIEW:'자동 반영 상한 초과 · 검토 필요',
  APPLIED:'이자 반영 완료', NO_CHANGE:'추가 이자 차액 없음',
  CHECKING:'확인 중', CHECK_FAILED_REVIEW:'처리 결과 확인 필요 · 이자 반영 이력 확인',
  WRITE_DISABLED_REVIEW:'조회 전용 · 장부 쓰기 차단', STATEMENT_REQUIRED:'은행 이자·입출금 명세 대조 필요',
  PROFILE_UNVERIFIED:'은행 명세 형식 검증 필요', STATEMENT_INCOMPLETE:'은행 명세 완전성 확인 필요',
  MOVEMENT_MISMATCH:'은행 입출금과 장부 불일치', INITIAL_BALANCE_REVIEW:'초기 누적 차액 검토 필요',
  LEDGER_UNVERIFIED:'장부 자금 이동 확인 필요', STATEMENT_BALANCE_MISMATCH:'명세 잔고 연결 확인 필요',
  BANK_CASH_CHAIN_MISMATCH:'은행 거래 전후 현금 연결 확인 필요', PRINCIPAL_MISMATCH:'CMA 원금 반환 금액 확인 필요',
  BANK_HISTORY_MISMATCH:'은행 거래·입출금 명세 불일치', INTEREST_POSTING_UNVERIFIED:'지급 이자 확정 근거 확인 필요',
  BUSINESS_STATUS_UNVERIFIED:'은행 업무 응답 확인 필요', TOTAL_UNVERIFIED:'계좌 총액과 잔고 항목 불일치',
  BOOKED_INTEREST_MISMATCH:'기존 이자 기록과 은행 명세 불일치',
  UNSUPPORTED_TRANSACTION:'지원되지 않는 은행 거래 검토 필요', MATCHED:'은행 명세와 장부 대조 완료',
})[state] || '확인 필요';

export function cmaCheckAlerts(data,now=new Date()) {
  const current=new Date(now),korean=new Date(current.getTime()+9*60*60*1000);
  const today=korean.toISOString().slice(0,10),ended=korean.getUTCHours()>=16;
  const alerts=[];
  for(const account of data?.accounts || []) {
    if(!account.enabled)continue;
    const rows=(data.checks || []).filter(row=>row.event_date===today &&
      (row.account_id?row.account_id===account.id:row.account_alias===account.account_alias));
    rows.sort((a,b)=>b.slot-a.slot);
    const latest=rows[0];
    if(!latest){if(ended)alerts.push(`${account.account_alias}: 오늘 자동 확인 기록이 없습니다.`);continue;}
    if(['APPLIED','NO_CHANGE'].includes(latest.state))continue;
    const needsReview=['CHECK_FAILED_REVIEW','WRITE_DISABLED_REVIEW','STATEMENT_REQUIRED','REVIEW_INTEREST','AUTO_LIMIT_REVIEW'].includes(latest.state);
    const stuck=latest.state==='CHECKING' && current-new Date(latest.updated_at)>10*60*1000;
    if(needsReview || stuck || ended || latest.slot===2)
      alerts.push(`${account.account_alias}: ${cmaStateLabel(latest.state)}. 오늘 이자 자동 처리가 완료되지 않았습니다.`);
  }
  return alerts;
}

export function cmaIncomeRequest(accountId, preview, confirmed, requestId) {
  if (!confirmed || !preview?.observation_id || !preview.book_token || !accountId || !requestId
      || preview.can_apply===false || !Number.isFinite(Number(preview.interest_krw)) || Number(preview.interest_krw) <= 0) {
    throw new Error('입출금 반영 여부와 CMA 이자 차액을 확인해주세요.');
  }
  return {request_id:requestId,account_id:accountId,observation_id:preview.observation_id,
    book_token:preview.book_token,interest_krw:preview.interest_krw,confirmed_movements:true};
}

export function cmaInitialInterestRequest(accountId,preview,confirmed,reason,requestId) {
  if(!accountId || !preview?.observation_id || !preview.book_token || !requestId || !confirmed
    || preview.status!=='INITIAL_BALANCE_REVIEW' || !Number.isFinite(Number(preview.prior_difference_krw))
    || Number(preview.prior_difference_krw)<=0 || (reason || '').trim().length<10) {
    throw new Error('이전 누적 차액이 이자임을 확인하고 초기 정리 사유를 입력해주세요.');
  }
  return {request_id:requestId,account_id:accountId,observation_id:preview.observation_id,
    book_token:preview.book_token,initial_interest_krw:preview.prior_difference_krw,
    confirmed_initial_interest:true,reason:reason.trim()};
}
