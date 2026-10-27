import React from 'react';
import PeriodPerformance from './PeriodPerformance';
import DepositMaturities from './DepositMaturities';
import DividendDetails from './DividendDetails';
import RealizedGainsPanel from './RealizedGainsPanel';
import HoldingsPerformance from './HoldingsPerformance';
import {holdingCurrent} from '../../utils/holdingHistory';

export default function AnalysisTab({ portfolioId, assets, dashboardData, performance, onOpenHistory }) {
  const accounts = dashboardData?.account_summaries || dashboardData?.accounts || [];
  return <div>
    <div className="section-card">
      <h2>분석 및 확인</h2>
      <p>선택한 포트폴리오의 기간 성과, 예금 만기와 배당 계산 내역을 확인합니다.</p>
    </div>
    <HoldingsPerformance scope={portfolioId} current={holdingCurrent(dashboardData?.kpi)} revision={dashboardData}/>
    <details className="section-card"><summary style={{cursor:'pointer',fontWeight:700}}>기준일 이후 운용 성과</summary>
      <PeriodPerformance portfolioId={portfolioId} performance={performance} onOpenHistory={onOpenHistory} />
    </details>
    <RealizedGainsPanel portfolioId={portfolioId} assets={assets || []} accounts={accounts} revision={dashboardData} />
    <DepositMaturities assets={assets || []} accounts={accounts} />
    <DividendDetails accounts={accounts} />
  </div>;
}
