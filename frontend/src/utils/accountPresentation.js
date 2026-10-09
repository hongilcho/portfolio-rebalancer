export function accountIssues(account){
  const issues=[];
  if(Number(account.deposit_krw)<0 || Number(account.deposit_usd)<0)issues.push('음수 예수금 확인 필요');
  if(account.account_type==='IRP'){
    if(account.risk_pct==null || !Number.isFinite(Number(account.risk_pct)))issues.push('IRP 위험자산 비중 확인 필요');
    else if(Number(account.risk_pct)>70)issues.push('IRP 위험자산 70% 초과');
  }
  if(Number(account.annual_limit_pct)>1)issues.push('연간 납입한도 초과');
  return issues;
}
export function remainingAnnualLimit(account){
  if(!(Number(account.annual_limit)>0) || account.annual_limit_pct==null || !Number.isFinite(Number(account.annual_limit_pct)))return null;
  return Math.max(0,Number(account.annual_limit)*(1-Number(account.annual_limit_pct)));
}
