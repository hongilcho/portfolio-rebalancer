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

export function accountWithoutDeposits(account,usdKrw){
  const holdings=(account.holdings || []).filter(h=>!h.is_deposit);
  const stockEval=holdings.reduce((sum,h)=>sum+(Number(h.eval_amount)||0),0);
  const stockBuy=holdings.reduce((sum,h)=>sum+(Number(h.buy_amount) || Number(h.avg_price)*Number(h.quantity) || 0),0);
  const dividends=holdings.reduce((sum,h)=>sum+(Number(h.dividend_profit_krw)||0),0);
  const holdingProfit=stockEval-stockBuy+dividends;
  const interest=account.account_type==='CMA'?(Number(account.cma_interest_krw)||0):0;
  return {...account,holdings,stock_eval:stockEval,stock_buy_total:stockBuy,
    eval_profit_krw:stockEval-stockBuy,dividend_profit_krw:dividends,
    profit_krw:holdingProfit+interest,total_profit_krw:holdingProfit+interest,
    profit_pct:stockBuy>0?holdingProfit/stockBuy*100:0,
    total_val:stockEval+(Number(account.deposit_krw)||0)+(Number(account.deposit_usd)||0)*(usdKrw||1380)};
}
