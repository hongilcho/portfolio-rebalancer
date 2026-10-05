import React, { useEffect, useState } from 'react';
import { api } from '../../utils/api';
import { formatKRW } from '../../utils/formatters';
import PerformanceChart from './PerformanceChart';

export default function PeriodPerformance({ portfolioId, performance, onOpenHistory }) {
  const { data, busy, error, notice, run, capture, setNotice } = performance;
  const [startChecked, setStartChecked] = useState(false);
  const [completeChecked, setCompleteChecked] = useState(false);
  const [open, setOpen] = useState(true);
  useEffect(() => { setCompleteChecked(false); }, [data]);
  const lastSnapshot = data?.snapshots?.at(-1);
  return <section className="section-card workflow-panel">
    <details open={open} onToggle={e => setOpen(e.currentTarget.open)}>
      <summary style={{ cursor: 'pointer', fontWeight: 700 }}>📈 월별·연간 기간 성과 {data?.tracking ? '· 기록 중' : '· 시작 기준 필요'}</summary>
      <p>예수금을 포함한 포트폴리오 전체의 기간 성과를 기록합니다. 기존 보유자산 수익률과 별도 지표입니다.</p>
      {error && <p role="alert">기간 성과: {error}</p>}{notice && <p>{notice}</p>}
      {!data ? <p>기간 성과 정보를 조회 중입니다.</p> : !data.tracking ? <div>
        <p>기준 등록 전 과거 수익률은 재구성하지 않습니다. 등록 후 이 포트폴리오를 열거나 새로고침하면 그날의 마지막 조회 평가액을 저장합니다. 앱을 사용하지 않은 날짜는 기록되지 않습니다.</p>
        <label style={{display:'block',margin:'16px 0 8px'}}><input type="checkbox" checked={startChecked} disabled={busy} onChange={e=>setStartChecked(e.target.checked)} />현재 장부의 잔고·예수금·시세를 확인했고, 이후 외부 입출금을 기록하겠습니다.</label>
        <button className="btn btn-primary" disabled={busy || !startChecked} onClick={()=>run(async()=>{await api.startPerformance(portfolioId);setNotice('현재 평가액을 시작 기준으로 등록했습니다.');})}>기간 성과 시작 기준 등록</button>
      </div> : <div>
        <p>시작 기준 {data.tracking.baseline_date} · {formatKRW(data.tracking.baseline_value)} · 평가 기록 {data.snapshots.length}일</p>
        <button className="btn btn-secondary" disabled={busy} onClick={()=>run(capture)}>현재 평가액 다시 기록</button>
        <p>외부 투자자금 입출금 기록 {data.flows.filter(f=>!f.voided).length}건 · 4번 ‘매매 및 입출금 기록’에서 입력·취소·복원합니다.</p>
        <button type="button" className="btn btn-secondary" onClick={onOpenHistory}>4. 매매 및 입출금 기록으로 이동</button>
        <label style={{display:'block',margin:'16px 0 8px'}}><input type="checkbox" checked={completeChecked} disabled={busy} onChange={e=>setCompleteChecked(e.target.checked)} />시작 기준부터 최근 평가일까지 외부 입출금을 모두 기록했고 실제 잔고도 반영했습니다. 입출금이 없으면 없음으로 확인합니다.</label>
        <button className="btn btn-secondary" disabled={busy || !completeChecked || !lastSnapshot} onClick={()=>run(()=>api.confirmPerformanceFlows(portfolioId,{revision:data.tracking.revision,through:lastSnapshot.snapshot_date,value:Number(lastSnapshot.value_krw)}))}>기간 입출금 기록 확인 완료</button>
        <PerformanceChart reports={data.reports} />
        <div className="table-container"><table className="custom-table"><thead><tr><th>구분</th><th>기간</th><th>평가 시작/종료</th><th>순입금</th><th>기간 손익</th><th>금액가중 기간 수익률</th></tr></thead><tbody>
          {data.reports.map(r=><tr key={`${r.kind}/${r.label}`}><td>{r.kind}</td><td>{r.label}{r.partial && ' (기준 등록 이후)'}<br />{r.start} ~ {r.end}</td><td>{r.start_value==null ? '미기록' : formatKRW(r.start_value)} / {r.end_value==null ? '미기록' : formatKRW(r.end_value)}</td><td>{r.net_flow==null ? '—' : formatKRW(r.net_flow)}</td><td>{r.profit==null ? '—' : formatKRW(r.profit)}{r.warning && <p>{r.warning}</p>}</td><td>{r.return_pct==null ? '계산 대기' : `${(Math.abs(r.return_pct)<0.005 ? 0 : r.return_pct).toFixed(2)}%`}</td></tr>)}
        </tbody></table></div>
      </div>}
      <details><summary>계산 방식·기록 범위 안내</summary>
        <p>선택한 포트폴리오의 보유자산·예금·원화/달러 예수금 전체를 원화로 평가합니다. 가상자산과 다른 포트폴리오는 제외합니다.</p>
        <p>배당은 실제 잔고에 반영된 금액으로만 포함합니다. 계산된 배당 손익을 평가액에 다시 더하지 않습니다. 앱에서 조회한 시점의 평가액이며 월말 종가를 보장하지 않습니다.</p>
        <p>기간 손익 = 종료 평가액 − 시작 평가액 − 순입금. 수익률은 날짜별 입출금을 반영한 금액가중 방식(XIRR의 기간 환산)이며 연환산 수익률·시간가중 수익률이 아닙니다. 같은 날의 입출금은 날짜 단위로 계산합니다. 단순 월 수익률 합산으로 연 수익률을 만들지 않습니다.</p>
        <p>월말·연말 경계일 평가액이 없으면 해당 기간을 계산하지 않습니다. 현재 월·연은 최근 기록일까지의 성과입니다. 입력한 현금 흐름·잔고 및 조회 시세의 정확도에 의존합니다.</p>
      </details>
    </details>
  </section>;
}
