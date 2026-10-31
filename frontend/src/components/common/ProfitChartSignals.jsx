import React from 'react';
import {profitTone,profitLabel,profitColor,signedProfit} from '../../utils/profitChartSignals';
import './ProfitChartSignals.css';
export function ProfitStatus({profit,rate,caption}){
  const value=Number.isFinite(profit)?profit:rate;
  return <div className="profit-chart-status" data-tone={profitTone(value)} aria-label={`${caption} 손익 상태`}>
    <div><span className="profit-chart-status-label">{caption}</span><strong className="profit-chart-state">{profitLabel(value)}</strong></div>
    <div className="profit-chart-status-values"><strong>{signedProfit(profit,'profit')}</strong><span>{signedProfit(rate,'return_pct')}</span></div>
  </div>;
}
export function ZeroLine({reference,left,right,y,top,bottom}){
  if(reference?.position!=='inside')return null;
  const labelY=Math.max(top+13,Math.min(bottom-6,y-7));
  return <g className="profit-chart-zero-line" aria-label={reference.label}>
    <line x1={left} x2={right} y1={y} y2={y} stroke="var(--text-secondary)" strokeWidth="1.6" strokeDasharray="5 4"/>
    <text x={right-3} y={labelY} textAnchor="end" fill="var(--text-primary)" stroke="var(--bg-card)" strokeWidth="4" paintOrder="stroke" fontSize="11">{reference.label}</text>
  </g>;
}
export function ZeroOutside({reference,position}){
  return reference?.position===position?<p className="profit-chart-zero-outside" data-position={position}>{reference.label}</p>:null;
}
export function SignedSelection({value,metric,children}){
  return <strong className={metric==='value_krw'?undefined:'profit-chart-selected'} style={metric==='value_krw'?undefined:{color:profitColor(value)}}>
    {metric!=='value_krw'&&<span className="profit-chart-selection-label">{profitLabel(value)} </span>}{children}
  </strong>;
}
