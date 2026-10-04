/** CryptoCombinedCards: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { Coins } from 'lucide-react';
import { formatKRW, formatPercent } from '../../utils/formatters';

export default function CryptoCombinedCards({
  hongilBtc,
  yoonaBtc,
  btcComb,
  hongilEth,
  yoonaEth,
  ethComb,
}) {
  return (
    <>
      {/* 3. 코인별 종합 합산 카드 (홍일 + 윤아 합산) */}
      <div className="section-card" style={{ border: '1px solid rgba(245, 158, 11, 0.3)' }}>
        <div className="section-title" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#F59E0B', fontWeight: 800 }}>
            <Coins size={18} />
            🪙 가상화폐 전체 종합 합산 (홍일 + 윤아 가중평균)
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            두 계정의 보유량을 통합하고 가중평균 매수평단가를 적용한 현황입니다.
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', marginTop: '16px' }}>
          {/* Combined BTC */}
          <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '1.2rem' }}>🪙</span>
                <div>
                  <div style={{ fontWeight: 800, fontSize: '1rem', color: '#F59E0B' }}>비트코인 합계 (BTC)</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>홍일: {hongilBtc.quantity || 0} + 윤아: {yoonaBtc.quantity || 0}</div>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 800, fontSize: '1.15rem', color: 'var(--accent-primary)' }}>
                  {formatKRW(btcComb.eval_amount)}
                </div>
                <div style={{ fontSize: '0.78rem', fontWeight: 700, color: (btcComb.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(btcComb.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(btcComb.profit_krw)} ({formatPercent(btcComb.profit_pct)})
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.86rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>현재가 (1 BTC)</span>
                <strong style={{ fontSize: '0.92rem' }}>
                  {formatKRW(btcComb.current_price)}
                  <span style={{ fontSize: '0.78rem', marginLeft: '5px', color: (btcComb.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                    {(btcComb.change_24h_pct || 0) >= 0 ? '+' : ''}{btcComb.change_24h_pct?.toFixed(2)}%
                  </span>
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>총 보유 수량</span>
                <strong>{btcComb.quantity ? Number(btcComb.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} BTC</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>가중평균 매수평단</span>
                <strong>{formatKRW(btcComb.avg_price)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>총 매입금액</span>
                <strong>{formatKRW(btcComb.buy_amount)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>총 평가금액</span>
                <strong style={{ color: 'var(--accent-primary)', fontSize: '0.95rem' }}>{formatKRW(btcComb.eval_amount)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: '6px', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontWeight: 600 }}>평가 손익 (수익률)</span>
                <strong style={{ color: (btcComb.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(btcComb.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(btcComb.profit_krw)} ({formatPercent(btcComb.profit_pct)})
                </strong>
              </div>
            </div>
          </div>

          {/* Combined ETH */}
          <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '1.2rem' }}>💎</span>
                <div>
                  <div style={{ fontWeight: 800, fontSize: '1rem', color: '#8B5CF6' }}>이더리움 합계 (ETH)</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>홍일: {hongilEth.quantity || 0} + 윤아: {yoonaEth.quantity || 0}</div>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 800, fontSize: '1.15rem', color: 'var(--accent-primary)' }}>
                  {formatKRW(ethComb.eval_amount)}
                </div>
                <div style={{ fontSize: '0.78rem', fontWeight: 700, color: (ethComb.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(ethComb.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(ethComb.profit_krw)} ({formatPercent(ethComb.profit_pct)})
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.86rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>현재가 (1 ETH)</span>
                <strong style={{ fontSize: '0.92rem' }}>
                  {formatKRW(ethComb.current_price)}
                  <span style={{ fontSize: '0.78rem', marginLeft: '5px', color: (ethComb.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                    {(ethComb.change_24h_pct || 0) >= 0 ? '+' : ''}{ethComb.change_24h_pct?.toFixed(2)}%
                  </span>
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>총 보유 수량</span>
                <strong>{ethComb.quantity ? Number(ethComb.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} ETH</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>가중평균 매수평단</span>
                <strong>{formatKRW(ethComb.avg_price)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>총 매입금액</span>
                <strong>{formatKRW(ethComb.buy_amount)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>총 평가금액</span>
                <strong style={{ color: 'var(--accent-primary)', fontSize: '0.95rem' }}>{formatKRW(ethComb.eval_amount)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: '6px', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontWeight: 600 }}>평가 손익 (수익률)</span>
                <strong style={{ color: (ethComb.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(ethComb.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(ethComb.profit_krw)} ({formatPercent(ethComb.profit_pct)})
                </strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
