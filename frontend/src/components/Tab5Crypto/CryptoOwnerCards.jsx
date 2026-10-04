/** CryptoOwnerCards: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { formatKRW, formatPercent } from '../../utils/formatters';

export default function CryptoOwnerCards({
  hongil,
  isHongilProfit,
  hongilBtc,
  hongilEth,
  yoona,
  isYoonaProfit,
  yoonaBtc,
  yoonaEth,
}) {
  return (
    <>
      {/* 3. 대시보드 비교형 듀얼 카드: [👨 홍일 계정] vs [👩 윤아 계정] */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '18px' }}>

        {/* ===================== [👨 홍일 계정 카드] ===================== */}
        <div className="section-card" style={{ border: '1px solid rgba(14, 165, 233, 0.35)', background: 'linear-gradient(180deg, rgba(14, 165, 233, 0.04) 0%, var(--bg-card) 100%)' }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(14, 165, 233, 0.2)', paddingBottom: '12px', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ width: '34px', height: '34px', borderRadius: '50%', background: 'rgba(14, 165, 233, 0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.25rem' }}>
                👨
              </div>
              <div>
                <div style={{ fontWeight: 800, fontSize: '1.05rem', color: '#0EA5E9' }}>홍일 계정 (업비트)</div>
                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>가상화폐 지분 {hongil.share_pct?.toFixed(1)}%</div>
              </div>
            </div>

            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                {formatKRW(hongil.total_eval)}
              </div>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: isHongilProfit ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                {isHongilProfit ? '+' : ''}{formatKRW(hongil.total_profit)} ({formatPercent(hongil.total_profit_pct)})
              </div>
            </div>
          </div>

          {/* Hongil Coins List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Hongil BTC */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>🪙</span>
                  <strong style={{ fontSize: '0.92rem', color: '#F59E0B' }}>비트코인 (BTC)</strong>
                </div>
                <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>
                  {formatKRW(hongilBtc.current_price)}
                  <span style={{ fontSize: '0.75rem', marginLeft: '4px', color: (hongilBtc.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                    {(hongilBtc.change_24h_pct || 0) >= 0 ? '+' : ''}{hongilBtc.change_24h_pct?.toFixed(2)}%
                  </span>
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.84rem' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>보유 수량: </span>
                  <strong>{hongilBtc.quantity ? Number(hongilBtc.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} BTC</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매수 평단: </span>
                  <strong>{formatKRW(hongilBtc.avg_price)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매입 금액: </span>
                  <strong>{formatKRW(hongilBtc.buy_amount)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>평가 금액: </span>
                  <strong style={{ color: 'var(--accent-primary)' }}>{formatKRW(hongilBtc.eval_amount)}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.84rem', marginTop: '6px', paddingTop: '6px', borderTop: '1px dashed var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>평가 손익:</span>
                <strong style={{ color: (hongilBtc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(hongilBtc.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(hongilBtc.profit_krw)} ({formatPercent(hongilBtc.profit_pct)})
                </strong>
              </div>
            </div>

            {/* Hongil ETH */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>💎</span>
                  <strong style={{ fontSize: '0.92rem', color: '#8B5CF6' }}>이더리움 (ETH)</strong>
                </div>
                <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>
                  {formatKRW(hongilEth.current_price)}
                  <span style={{ fontSize: '0.75rem', marginLeft: '4px', color: (hongilEth.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                    {(hongilEth.change_24h_pct || 0) >= 0 ? '+' : ''}{hongilEth.change_24h_pct?.toFixed(2)}%
                  </span>
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.84rem' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>보유 수량: </span>
                  <strong>{hongilEth.quantity ? Number(hongilEth.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} ETH</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매수 평단: </span>
                  <strong>{formatKRW(hongilEth.avg_price)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매입 금액: </span>
                  <strong>{formatKRW(hongilEth.buy_amount)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>평가 금액: </span>
                  <strong style={{ color: 'var(--accent-primary)' }}>{formatKRW(hongilEth.eval_amount)}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.84rem', marginTop: '6px', paddingTop: '6px', borderTop: '1px dashed var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>평가 손익:</span>
                <strong style={{ color: (hongilEth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(hongilEth.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(hongilEth.profit_krw)} ({formatPercent(hongilEth.profit_pct)})
                </strong>
              </div>
            </div>
          </div>
        </div>

        {/* ===================== [👩 윤아 계정 카드] ===================== */}
        <div className="section-card" style={{ border: '1px solid rgba(236, 72, 153, 0.35)', background: 'linear-gradient(180deg, rgba(236, 72, 153, 0.03) 0%, var(--bg-card) 100%)' }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(236, 72, 153, 0.2)', paddingBottom: '12px', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(236, 72, 153, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.1rem' }}>
                👩
              </div>
              <div>
                <div style={{ fontWeight: 800, fontSize: '1.05rem', color: '#EC4899' }}>윤아 계정 (업비트)</div>
                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>가상화폐 지분 {yoona.share_pct?.toFixed(1)}%</div>
              </div>
            </div>

            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                {formatKRW(yoona.total_eval)}
              </div>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: isYoonaProfit ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                {isYoonaProfit ? '+' : ''}{formatKRW(yoona.total_profit)} ({formatPercent(yoona.total_profit_pct)})
              </div>
            </div>
          </div>

          {/* Yoona Coins List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Yoona BTC */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>🪙</span>
                  <strong style={{ fontSize: '0.92rem', color: '#F59E0B' }}>비트코인 (BTC)</strong>
                </div>
                <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>
                  {formatKRW(yoonaBtc.current_price)}
                  <span style={{ fontSize: '0.75rem', marginLeft: '4px', color: (yoonaBtc.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                    {(yoonaBtc.change_24h_pct || 0) >= 0 ? '+' : ''}{yoonaBtc.change_24h_pct?.toFixed(2)}%
                  </span>
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.84rem' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>보유 수량: </span>
                  <strong>{yoonaBtc.quantity ? Number(yoonaBtc.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} BTC</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매수 평단: </span>
                  <strong>{formatKRW(yoonaBtc.avg_price)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매입 금액: </span>
                  <strong>{formatKRW(yoonaBtc.buy_amount)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>평가 금액: </span>
                  <strong style={{ color: 'var(--accent-primary)' }}>{formatKRW(yoonaBtc.eval_amount)}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.84rem', marginTop: '6px', paddingTop: '6px', borderTop: '1px dashed var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>평가 손익:</span>
                <strong style={{ color: (yoonaBtc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(yoonaBtc.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(yoonaBtc.profit_krw)} ({formatPercent(yoonaBtc.profit_pct)})
                </strong>
              </div>
            </div>

            {/* Yoona ETH */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>💎</span>
                  <strong style={{ fontSize: '0.92rem', color: '#8B5CF6' }}>이더리움 (ETH)</strong>
                </div>
                <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>
                  {formatKRW(yoonaEth.current_price)}
                  <span style={{ fontSize: '0.75rem', marginLeft: '4px', color: (yoonaEth.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                    {(yoonaEth.change_24h_pct || 0) >= 0 ? '+' : ''}{yoonaEth.change_24h_pct?.toFixed(2)}%
                  </span>
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.84rem' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>보유 수량: </span>
                  <strong>{yoonaEth.quantity ? Number(yoonaEth.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} ETH</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매수 평단: </span>
                  <strong>{formatKRW(yoonaEth.avg_price)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>매입 금액: </span>
                  <strong>{formatKRW(yoonaEth.buy_amount)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>평가 금액: </span>
                  <strong style={{ color: 'var(--accent-primary)' }}>{formatKRW(yoonaEth.eval_amount)}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.84rem', marginTop: '6px', paddingTop: '6px', borderTop: '1px dashed var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>평가 손익:</span>
                <strong style={{ color: (yoonaEth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  {(yoonaEth.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(yoonaEth.profit_krw)} ({formatPercent(yoonaEth.profit_pct)})
                </strong>
              </div>
            </div>
          </div>
        </div>

      </div>
    </>
  );
}
