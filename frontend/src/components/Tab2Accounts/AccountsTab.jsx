import React,{useMemo,useState} from 'react';
import AccountBreakdown from '../Tab1Dashboard/AccountBreakdown';
import MarketStatus from '../common/MarketStatus';
import {useCompactLayout} from '../../utils/useCompactLayout';
export default function AccountsTab({dashboardData,currencyMode='KRW'}){
  const compact=useCompactLayout();
  const [expandedAccs,setExpandedAccs]=useState({});
  const [includeDeposits,setIncludeDeposits]=useState(()=>{try{return JSON.parse(sessionStorage.getItem('dashboard_include_deposits') ?? 'true');}catch{return true;}});
  const accSummaries=useMemo(()=>dashboardData?.account_summaries || dashboardData?.accounts || [],[dashboardData]);
  const usd_krw=dashboardData?.usd_krw || 1380;
  // 계좌별 자산 현황 (예금 제외 모드 시 정기예금 계좌 및 각 계좌의 예금 자산 제외)
  const displayAccSummaries = useMemo(() => {
    if (includeDeposits) return accSummaries;
    return (accSummaries || [])
      .filter((acc) => acc.account_type !== '정기예금')
      .map((acc) => {
        const nonDepositHoldings = (acc.holdings || []).filter((h) => !h.is_deposit);
        const stockEval = nonDepositHoldings.reduce((sum, h) => sum + (Number(h.eval_amount) || 0), 0);
        const stockBuy = nonDepositHoldings.reduce((sum, h) => sum + (Number(h.avg_price) * Number(h.quantity) || 0), 0);
        const profitKrw = stockEval - stockBuy;
        const profitPct = stockBuy > 0 ? (profitKrw / stockBuy * 100) : 0;
        const totalVal = stockEval + (Number(acc.deposit_krw) || 0) + ((Number(acc.deposit_usd) || 0) * (usd_krw || 1380));
        return {
          ...acc,
          holdings: nonDepositHoldings,
          stock_eval: stockEval,
          stock_buy_total: stockBuy,
          profit_krw: profitKrw,
          profit_pct: profitPct,
          total_val: totalVal
        };
      });
  }, [accSummaries, includeDeposits, usd_krw]);


  if(!dashboardData)return <p>계좌 현황을 불러오는 중입니다.</p>;
  const toggleAccordion=id=>setExpandedAccs(previous=>{const next=!(previous[id] ?? !compact);return compact?{[id]:next}:{...previous,[id]:next};});
  return <div className="accounts-workspace"><MarketStatus status={dashboardData.market_status}/>
    <label className="account-filter"><input type="checkbox" checked={includeDeposits} onChange={e=>{setIncludeDeposits(e.target.checked);try{sessionStorage.setItem('dashboard_include_deposits',JSON.stringify(e.target.checked));}catch{}}}/>예금 포함</label>
    <AccountBreakdown includeDeposits={includeDeposits} displayAccSummaries={displayAccSummaries} expandedAccs={expandedAccs} usd_krw={usd_krw} toggleAccordion={toggleAccordion} currencyMode={currencyMode} compact={compact}/>
  </div>;
}
