import React from 'react';
import {formatKRW,getProfitColor} from '../../utils/formatters';
import {saleProfit} from '../../utils/realizedReport';
import '../Tab6Analysis/RealizedReport.css';
const money=v=>v==null?'확인 필요':formatKRW(v);
export default function RealizedProfitSummary({dashboardData,onOpenRealized}){
  const kpi=dashboardData?.kpi||{},summary=dashboardData?.realized_summary,latest=dashboardData?.realized_recent_sales||[];
  if(!summary)return null;
  return <section className="section-card profit-overview" aria-label="평가손익과 실현손익 요약">
    <div className="profit-report-heading"><h3>보유손익과 매도손익</h3><small>원화 기준 · 서로 다른 범위</small></div>
    <div className="profit-overview-cards"><div><span>보유분 평가손익</span><strong style={{color:getProfitColor(kpi.total_eval_profit)}}>{money(kpi.total_eval_profit)}</strong><small>현재 보유 수량 기준</small></div><div><span>누적 실현 매도손익 · 비용 전</span><strong style={{color:getProfitColor(summary.gross_profit_krw)}}>{money(summary.gross_profit_krw)}</strong><small>{summary.sell_count}건 · 비용·원가 확인 필요 {summary.pending_count}건</small></div><div><span>보유종목 배당</span><strong>{money(kpi.total_dividend_profit)}</strong><small>매도손익과 별도</small></div></div>
    {latest.length>0&&<div className="profit-recent-sales"><small>최근 매도</small>{latest.map(row=>{const p=saleProfit(row);return <div key={row.trade_id}><span>{row.trade_date} · {row.asset_name} {row.quantity}주</span><strong style={{color:getProfitColor(p.amount)}}>{money(p.amount)}<small>{p.label}</small></strong></div>;})}</div>}
    {onOpenRealized&&<button type="button" className="btn btn-secondary" onClick={onOpenRealized}>7번에서 실현손익 보고서 보기</button>}
    <details><summary>손익 범위와 비용 기준</summary><p>평가손익은 현재 보유분, 실현손익은 기록된 과거 매도분입니다. 배당은 현재 보유종목의 기존 계산 범위입니다. 기간이 달라 위 금액을 전체 운용손익으로 단순 합산하지 않습니다.</p><p>비용 확인 완료분 순손익 {money(summary.confirmed_net_profit_krw)}. 기록한 CMA 이자는 계좌 현황에서 별도로 확인합니다. 매도대금은 예수금에 이미 반영되므로 실현손익을 총자산에 다시 더하지 않습니다.</p></details>
  </section>;
}
