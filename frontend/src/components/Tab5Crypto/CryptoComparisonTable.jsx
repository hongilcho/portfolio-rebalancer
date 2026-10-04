/** CryptoComparisonTable: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { formatKRW, formatPercent } from '../../utils/formatters';

export default function CryptoComparisonTable({
  hongilBtc,
  hongilEth,
  hongil,
  isHongilProfit,
  yoonaBtc,
  yoonaEth,
  yoona,
  isYoonaProfit,
  cryptoTotal,
  isCryptoProfit,
}) {
  return (
    <>
      {/* 4. Detailed Comparison Table */}
      <div className="section-card">
        <div className="section-title">
          <span>📊 계정별 가상화폐 세부 보유 및 비중 현황</span>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>자산 구분</th>
                <th>소유자</th>
                <th>보유량 / 세부내용</th>
                <th>총 매입금액(원)</th>
                <th>현재 평가금액(원)</th>
                <th>평가 손익(원)</th>
                <th>수익률(%)</th>
                <th>가상화폐 내 비중(%)</th>
              </tr>
            </thead>
            <tbody>
              {/* 1) Hongil BTC */}
              <tr>
                <td style={{ fontWeight: 600, color: '#F59E0B', paddingLeft: '20px' }}>
                  🪙 비트코인 (BTC)
                </td>
                <td><span className="badge" style={{ background: 'rgba(14, 165, 233, 0.15)', color: '#0EA5E9', fontWeight: 700 }}>👨 홍일</span></td>
                <td>{hongilBtc.quantity ? Number(hongilBtc.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} BTC</td>
                <td>{formatKRW(hongilBtc.buy_amount)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(hongilBtc.eval_amount)}</td>
                <td style={{ color: (hongilBtc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {(hongilBtc.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(hongilBtc.profit_krw)}
                </td>
                <td style={{ color: (hongilBtc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(hongilBtc.profit_pct)}
                </td>
                <td>{hongilBtc.weight_in_crypto_pct?.toFixed(2)}%</td>
              </tr>

              {/* 2) Hongil ETH */}
              <tr>
                <td style={{ fontWeight: 600, color: '#8B5CF6', paddingLeft: '20px' }}>
                  💎 이더리움 (ETH)
                </td>
                <td><span className="badge" style={{ background: 'rgba(14, 165, 233, 0.15)', color: '#0EA5E9', fontWeight: 700 }}>👨 홍일</span></td>
                <td>{hongilEth.quantity ? Number(hongilEth.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} ETH</td>
                <td>{formatKRW(hongilEth.buy_amount)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(hongilEth.eval_amount)}</td>
                <td style={{ color: (hongilEth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {(hongilEth.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(hongilEth.profit_krw)}
                </td>
                <td style={{ color: (hongilEth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(hongilEth.profit_pct)}
                </td>
                <td>{hongilEth.weight_in_crypto_pct?.toFixed(2)}%</td>
              </tr>

              {/* 3) Hongil Subtotal */}
              <tr style={{ background: 'rgba(14, 165, 233, 0.04)', fontStyle: 'italic' }}>
                <td style={{ fontWeight: 700, paddingLeft: '28px', color: '#0EA5E9' }}>
                  ↳ 👨 홍일 가상화폐 소계
                </td>
                <td style={{ fontWeight: 700, color: '#0EA5E9' }}>홍일 합계</td>
                <td>BTC + ETH</td>
                <td>{formatKRW(hongil.total_buy)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(hongil.total_eval)}</td>
                <td style={{ color: isHongilProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {isHongilProfit ? '+' : ''}{formatKRW(hongil.total_profit)}
                </td>
                <td style={{ color: isHongilProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(hongil.total_profit_pct)}
                </td>
                <td style={{ fontWeight: 700, color: '#0EA5E9' }}>
                  {hongil.share_pct?.toFixed(2)}%
                </td>
              </tr>

              {/* 4) Yoona BTC */}
              <tr>
                <td style={{ fontWeight: 600, color: '#F59E0B', paddingLeft: '20px' }}>
                  🪙 비트코인 (BTC)
                </td>
                <td><span className="badge" style={{ background: 'rgba(236, 72, 153, 0.15)', color: '#EC4899', fontWeight: 700 }}>👩 윤아</span></td>
                <td>{yoonaBtc.quantity ? Number(yoonaBtc.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} BTC</td>
                <td>{formatKRW(yoonaBtc.buy_amount)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(yoonaBtc.eval_amount)}</td>
                <td style={{ color: (yoonaBtc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {(yoonaBtc.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(yoonaBtc.profit_krw)}
                </td>
                <td style={{ color: (yoonaBtc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(yoonaBtc.profit_pct)}
                </td>
                <td>{yoonaBtc.weight_in_crypto_pct?.toFixed(2)}%</td>
              </tr>

              {/* 5) Yoona ETH */}
              <tr>
                <td style={{ fontWeight: 600, color: '#8B5CF6', paddingLeft: '20px' }}>
                  💎 이더리움 (ETH)
                </td>
                <td><span className="badge" style={{ background: 'rgba(236, 72, 153, 0.15)', color: '#EC4899', fontWeight: 700 }}>👩 윤아</span></td>
                <td>{yoonaEth.quantity ? Number(yoonaEth.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} ETH</td>
                <td>{formatKRW(yoonaEth.buy_amount)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(yoonaEth.eval_amount)}</td>
                <td style={{ color: (yoonaEth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {(yoonaEth.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(yoonaEth.profit_krw)}
                </td>
                <td style={{ color: (yoonaEth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(yoonaEth.profit_pct)}
                </td>
                <td>{yoonaEth.weight_in_crypto_pct?.toFixed(2)}%</td>
              </tr>

              {/* 6) Yoona Subtotal */}
              <tr style={{ background: 'rgba(236, 72, 153, 0.04)', fontStyle: 'italic' }}>
                <td style={{ fontWeight: 700, paddingLeft: '28px', color: '#EC4899' }}>
                  ↳ 👩 윤아 가상화폐 소계
                </td>
                <td style={{ fontWeight: 700, color: '#EC4899' }}>윤아 합계</td>
                <td>BTC + ETH</td>
                <td>{formatKRW(yoona.total_buy)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(yoona.total_eval)}</td>
                <td style={{ color: isYoonaProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {isYoonaProfit ? '+' : ''}{formatKRW(yoona.total_profit)}
                </td>
                <td style={{ color: isYoonaProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(yoona.total_profit_pct)}
                </td>
                <td style={{ fontWeight: 700, color: '#EC4899' }}>
                  {yoona.share_pct?.toFixed(2)}%
                </td>
              </tr>

              {/* 7) Grand Crypto Total Row */}
              <tr className="total-row" style={{ fontSize: '1rem' }}>
                <td style={{ fontWeight: 800 }}>🌟 🪙 가상화폐 전체 총계</td>
                <td style={{ fontWeight: 800 }}>홍일 + 윤아</td>
                <td>BTC + ETH 종합</td>
                <td>{formatKRW(cryptoTotal.total_buy)}</td>
                <td style={{ fontWeight: 800, color: 'var(--accent-primary)' }}>{formatKRW(cryptoTotal.total_eval)}</td>
                <td style={{ color: isCryptoProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {isCryptoProfit ? '+' : ''}{formatKRW(cryptoTotal.total_profit)}
                </td>
                <td style={{ color: isCryptoProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {formatPercent(cryptoTotal.total_profit_pct)}
                </td>
                <td style={{ fontWeight: 800 }}>100.00%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
