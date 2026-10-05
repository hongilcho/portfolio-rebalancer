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
      <summary style={{ cursor: 'pointer', fontWeight: 700 }}>📈 일별·월별·연간 기간 성과 {data?.tracking ? '· 기록 중' : '· 시작 기준 필요'}</summary>
      <p>예수금을 포함한 포트폴리오 전체의 기간 성과를 기록합니다. 기존 보유자산 수익률과 별도 지표입니다.</p>
      {error && <p role="alert">기간 성과: {error}</p>}{notice && <p>{notice}</p>}
      {!data ? <p>기간 성과 정보를 조회 중입니다.</p> : !data.tracking ? <div>
        <p>기준 등록 전 과거 수익률은 재구성하지 않습니다. 등록 후 백엔드가 KRX 거래일 오후 4시(한국 시간)에 종가 평가액을 자동 기록합니다. 앱을 열지 않아도 서버가 실행 중이면 기록됩니다.</p>
        <label style={{display:'block',margin:'16px 0 8px'}}><input type="checkbox" checked={startChecked} disabled={busy} onChange={e=>setStartChecked(e.target.checked)} />현재 장부의 잔고·예수금·시세를 확인했고, 이후 외부 입출금을 기록하겠습니다.</label>
        <button className="btn btn-primary" disabled={busy || !startChecked} onClick={()=>run(async()=>{await api.startPerformance(portfolioId);setNotice('현재 평가액을 시작 기준으로 등록했습니다.');})}>기간 성과 시작 기준 등록</button>
      </div> : <div>
        <p>시작 기준 {data.tracking.baseline_date} · {formatKRW(data.tracking.baseline_value)} · 평가 기록 {data.snapshots.length}일</p>
        <p>종가 자동 기록 {data.close_schedule?.enabled ? '사용 중' : data.close_schedule?.error ? '달력 확인 필요' : '꺼짐'}{data.close_schedule?.next_at && ` · ${data.close_schedule.enabled ? '다음 예정' : '다음 거래일 기준'} ${new Date(data.close_schedule.next_at).toLocaleString('ko-KR', {timeZone:'Asia/Seoul'})} (한국 시간)`}</p>
        {data.close_schedule?.error && <p role="alert">{data.close_schedule.error}</p>}
        {data.close_jobs?.[0] && <p>최근 수집 {data.close_jobs[0].snapshot_date} · {{pending:'수집 대기',running:'수집 중',retry:'5분 간격 재시도',complete:'기록 완료',missed:'미기록'}[data.close_jobs[0].state]}{data.close_jobs[0].error && ` · ${data.close_jobs[0].error}`}</p>}
        {data.missed_close_count>0 && <p>종가 미기록 {data.missed_close_count}일 · 당시 장부·환율이 없는 날짜는 현재 잔고로 복원하지 않습니다.</p>}
        <button className="btn btn-secondary" disabled={busy} onClick={()=>run(capture)}>오늘 종가 기록 재시도·장부 반영</button>
        <p>당일 종가 기록 시각 이후에 사용합니다. 늦게 입력한 매매·잔고는 이 버튼으로 당일 기록에 반영합니다. 이미 수집한 종가·환율을 유지하며 이전 기록도 보존합니다. 지난 날짜의 장부는 자동 수정하지 않습니다.</p>
        <p>외부 투자자금 입출금 기록 {data.flows.filter(f=>!f.voided).length}건 · 4번 ‘매매 및 입출금 기록’에서 입력·취소·복원합니다.</p>
        <button type="button" className="btn btn-secondary" onClick={onOpenHistory}>4. 매매 및 입출금 기록으로 이동</button>
        <label style={{display:'block',margin:'16px 0 8px'}}><input type="checkbox" checked={completeChecked} disabled={busy} onChange={e=>setCompleteChecked(e.target.checked)} />시작 기준부터 최근 평가일까지 외부 입출금을 모두 기록했고 실제 잔고도 반영했습니다. 입출금이 없으면 없음으로 확인합니다.</label>
        <button className="btn btn-secondary" disabled={busy || !completeChecked || !lastSnapshot} onClick={()=>run(()=>api.confirmPerformanceFlows(portfolioId,{revision:data.tracking.revision,through:lastSnapshot.snapshot_date,value:Number(lastSnapshot.value_krw)}))}>기간 입출금 기록 확인 완료</button>
        <PerformanceChart reports={data.reports} dailyReports={data.daily_reports || []} />
        <div className="table-container"><table className="custom-table"><thead><tr><th>구분</th><th>기간</th><th>평가 시작/종료</th><th>순입금</th><th>기간 손익</th><th>금액가중 기간 수익률</th></tr></thead><tbody>
          {data.reports.map(r=><tr key={`${r.kind}/${r.label}`}><td>{r.kind}</td><td>{r.label}{r.partial && ' (기준 등록 이후)'}<br />{r.start} ~ {r.end}</td><td>{r.start_value==null ? '미기록' : formatKRW(r.start_value)} / {r.end_value==null ? '미기록' : formatKRW(r.end_value)}</td><td>{r.net_flow==null ? '—' : formatKRW(r.net_flow)}</td><td>{r.profit==null ? '—' : formatKRW(r.profit)}{r.warning && <p>{r.warning}</p>}</td><td>{r.return_pct==null ? '계산 대기' : `${(Math.abs(r.return_pct)<0.005 ? 0 : r.return_pct).toFixed(2)}%`}</td></tr>)}
        </tbody></table></div>
      </div>}
      <details><summary>계산 방식·기록 범위 안내</summary>
        <p>선택한 포트폴리오의 보유자산·예금·원화/달러 예수금 전체를 원화로 평가합니다. 가상자산과 다른 포트폴리오는 제외합니다.</p>
        <p>국내 자산은 해당 거래일 KRX 정규장 종가, 미국 자산은 한국 평가 시점까지 마감한 최근 미국 정규장 종가를 적용합니다. 환율은 별도 고시 환율과 수집 시각을 함께 저장합니다. 예금은 평가일의 세후 원리금으로 계산합니다. 마감이 늦춰진 거래일에는 마감 30분 후 기록합니다.</p>
        <p>보유 수량·예수금은 수집 당시 앱 장부 기준입니다. 실제 매매·잔고를 종가 기록 전에 반영해주세요. 배당은 실제 잔고에 반영된 금액으로만 포함하며 계산된 배당 손익을 다시 더하지 않습니다. 기존 조회 기록과 시작 기준은 종가 기록과 구분해 보존합니다.</p>
        <p>기간 손익 = 종료 평가액 − 시작 평가액 − 순입금. 수익률은 날짜별 입출금을 반영한 금액가중 방식(XIRR의 기간 환산)이며 연환산 수익률·시간가중 수익률이 아닙니다. 같은 날의 입출금은 날짜 단위로 계산합니다. 단순 월 수익률 합산으로 연 수익률을 만들지 않습니다.</p>
        <p>종가 기록의 월말·연말 경계는 마지막 KRX 거래일입니다. 해당 거래일 기록이 없으면 기간 수익률을 계산하지 않습니다. 휴장일은 기록하지 않으며 누락된 거래일은 그래프의 선을 끊습니다. 현재 월·연은 최근 기록일까지의 성과이고, 입출금은 표시된 실제 평가 시작/종료 날짜 사이를 반영합니다.</p>
      </details>
    </details>
  </section>;
}
