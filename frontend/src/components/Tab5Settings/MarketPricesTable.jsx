/** MarketPricesTable: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Activity } from 'lucide-react';
import { formatKRW, formatUSD } from '../../utils/formatters';

export default function MarketPricesTable({
  setIsDiagnosticsOpen,
  assets,
  pricesData,
  accountMapById,
}) {
  return (
    <>
      {/* 1. Live Market Prices Grid */}
      <div className="section-card">
        <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>📊 실시간 시세 현황 & 자산별 상태 모니터링</span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setIsDiagnosticsOpen(true)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <Activity size={15} style={{ color: 'var(--accent-primary)' }} />
            <span>서버 속도 및 통신 진단</span>
          </button>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>종목명</th>
                <th>티커 / 계좌번호</th>
                <th>위험구분</th>
                <th>시장</th>
                <th>목표비중(%)</th>
                <th>현재가(현지)</th>
                <th>원화 환산가</th>
                <th>운용 가능 계좌</th>
                <th>시세 상태</th>
              </tr>
            </thead>
            <tbody>
              {assets && assets.length > 0 ? (
                assets.map((item) => {
                  const isUs = item.market === 'US';
                  const pInfo = (pricesData?.prices || []).find((p) => String(p.id) === String(item.id) || (item.ticker && p.ticker === item.ticker)) || {};
                  const priceNative = pInfo.price_native || 0;
                  const priceKrw = pricesData?.price_map?.[String(item.id)] ?? pInfo.price_krw ?? 0;
                  const status = pInfo.status || '대기중';
                  const nativePriceStr = isUs ? formatUSD(priceNative) : formatKRW(priceNative);

                  const mappedAccs = (item.allowed_accounts || [])
                    .map((id) => accountMapById[String(id)])
                    .filter(Boolean);

                  return (
                    <tr key={item.id}>
                      <td style={{ fontWeight: 700 }}>
                        {item.name}
                        {item.is_deposit && (
                          <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                            🏦 예금
                          </span>
                        )}
                        {item.include_in_rebalance === false && (
                          <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(156, 163, 175, 0.2)', color: 'var(--text-muted)' }}>
                            비중 제외
                          </span>
                        )}
                        {item.is_dividend_cost_deduct && (
                          <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(99, 102, 241, 0.2)', color: '#818CF8' }}>
                            💰 배당차감
                          </span>
                        )}
                      </td>
                      <td>{item.is_deposit ? (item.account_no || '-') : item.ticker}</td>
                      <td>
                        <span className={`badge ${item.is_risk_asset !== false ? 'badge-risk' : 'badge-safe'}`}>
                          {item.is_risk_asset !== false ? '🔴 위험' : '🟢 안전'}
                        </span>
                      </td>
                      <td>{isUs ? '🇺🇸 미국' : '🇰🇷 국내'}</td>
                      <td style={{ fontWeight: 600 }}>{(item.target_weight || 0).toFixed(1)}%</td>
                      <td>{nativePriceStr}</td>
                      <td style={{ fontWeight: 700 }}>{formatKRW(priceKrw)}</td>
                      <td>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', maxWidth: '280px' }}>
                          {mappedAccs.length > 0 ? (
                            mappedAccs.map((accName, i) => (
                              <span key={i} className="badge" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)', fontSize: '0.72rem' }}>
                                {accName}
                              </span>
                            ))
                          ) : item.is_deposit ? (
                            <span className="badge badge-safe" style={{ fontSize: '0.72rem' }}>단독 자산 (운용계좌 불필요)</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>지정 계좌 없음</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: '#A5B4FC' }}>
                          {status}
                        </span>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-secondary)' }}>
                    현재 포트폴리오에 등록된 자산(종목)이 없습니다. 아래 &apos;자산(종목) 마스터 관리&apos;에서 종목을 추가해 주세요.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
