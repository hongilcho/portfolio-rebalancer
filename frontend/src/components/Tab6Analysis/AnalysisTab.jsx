import React,{useCallback,useEffect,useRef} from 'react';
import PeriodPerformance from './PeriodPerformance';
import DepositMaturities from './DepositMaturities';
import DividendDetails from './DividendDetails';
import RealizedGainsPanel from './RealizedGainsPanel';
import HoldingsPerformance from './HoldingsPerformance';
import {holdingCurrent} from '../../utils/holdingHistory';
import {useLedgerRead} from '../../utils/useLedgerRead';

export default function AnalysisTab({ portfolioId, assets, dashboardData, performance, onOpenHistory, focusRequest }) {
  const holdingRef=useRef(null),periodRef=useRef(null),realizedRef=useRef(null);
  const realized = useLedgerRead('realized', portfolioId);
  const jump=useCallback(section=>{requestAnimationFrame(()=>({holding:holdingRef,period:periodRef,realized:realizedRef}[section]?.current?.scrollIntoView?.({behavior:'smooth',block:'start'})));},[]);
  useEffect(()=>{if(focusRequest)jump(focusRequest.section);},[focusRequest,jump]);
  const accounts = dashboardData?.account_summaries || dashboardData?.accounts || [];
  return <div>
    <div className="section-card">
      <h2>분석 및 확인</h2>
      <p>보유 중인 자산의 손익, 매도로 확정된 손익, 기준일 이후 전체 운용성과를 구분해 확인합니다.</p>
    </div>
    <nav className="profit-scope-navigation" aria-label="손익 분석 구분"><button type="button" className="btn btn-secondary" onClick={()=>jump('period')}>매도분 포함 기간 운용성과</button><button type="button" className="btn btn-secondary" onClick={()=>jump('holding')}>현재 보유자산 손익</button><button type="button" className="btn btn-secondary" onClick={()=>jump('realized')}>실현 매도손익 보고서</button></nav>
    <div ref={periodRef}>
      <PeriodPerformance portfolioId={portfolioId} performance={performance} onOpenHistory={onOpenHistory}
        sales={realized.data?.sales} salesError={realized.error} />
    </div>
    <div ref={holdingRef}><HoldingsPerformance scope={portfolioId} current={holdingCurrent(dashboardData?.kpi)} onOpenPeriod={()=>jump('period')}/></div>
    <div ref={realizedRef}><RealizedGainsPanel portfolioId={portfolioId} assets={assets || []} accounts={accounts} focusRequest={focusRequest}/></div>
    <DepositMaturities assets={assets || []} accounts={accounts} />
    <DividendDetails accounts={accounts} />
  </div>;
}
