import React, { useState, useEffect } from 'react';
import { 
  Coins, TrendingUp, TrendingDown, RefreshCw, Edit3, 
  ArrowUpRight, ArrowDownRight, PieChart, ShieldCheck, Sparkles 
} from 'lucide-react';
import { api } from '../../utils/api';
import { formatKRW, formatPercent } from '../../utils/formatters';
import EditCryptoModal from './EditCryptoModal';

export default function CryptoTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  const loadCryptoSummary = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      const res = await api.getCryptoSummary();
      setData(res);
    } catch (err) {
      console.error('Failed to load crypto summary:', err);
      setError(err.message || '가상화폐 데이터를 불러오는 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadCryptoSummary();
  }, []);

  const handleSaveHoldings = async (holdings) => {
    await api.updateCryptoHoldings(holdings);
    await loadCryptoSummary(true);
  };

  if (loading && !data) {
    return (
      <div className="section-card" style={{ textAlign: 'center', padding: '60px 20px' }}>
        <RefreshCw size={28} className="animate-spin" style={{ margin: '0 auto 12px', color: 'var(--accent-primary)' }} />
        <p style={{ color: 'var(--text-secondary)' }}>실시간 가상화폐 시세 및 자산 현황을 불러오는 중입니다...</p>
      </div>
    );
  }

  const cryptoAssets = data?.crypto_assets || [];
  const cryptoTotal = data?.crypto_total || {};
  const portfolioSummary = data?.portfolio_summary || {};
  const combined = data?.combined_summary || {};

  const isCombinedProfit = (combined.total_profit || 0) >= 0;
  const isCryptoProfit = (cryptoTotal.total_profit || 0) >= 0;
  const isPortfolioProfit = (portfolioSummary.total_profit || 0) >= 0;

  const btc = cryptoAssets.find(a => a.symbol === 'BTC') || {};
  const eth = cryptoAssets.find(a => a.symbol === 'ETH') || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Action Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Coins size={24} color="#F59E0B" />
            가상화폐(비트코인/이더리움) & 통합 전체 자산
          </h2>
          <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            기존 금융 포트폴리오와 가상화폐를 합산한 전체 가문 자산 현황을 조회합니다.
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button 
            className="btn btn-secondary btn-sm"
            onClick={() => loadCryptoSummary(true)}
            disabled={refreshing}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            title="실시간 시세 새로고침"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? '조회 중...' : '시세 새로고침'}
          </button>

          <button 
            className="btn btn-primary btn-sm"
            onClick={() => setIsEditModalOpen(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <Edit3 size={14} />
            보유량/평단가 수정
          </button>
        </div>
      </div>

      {error && (
        <div className="alert-banner alert-danger">
          <span>{error}</span>
        </div>
      )}

      {/* 1. Combined Total Asset Overview (포트폴리오 + 가상화폐) */}
      <div className="section-card" style={{ background: 'linear-gradient(145deg, var(--bg-card), rgba(99, 102, 241, 0.04))', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
        <div className="section-title" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-primary)', fontWeight: 800 }}>
            <Sparkles size={18} />
            🌟 통합 전체 자산 요약 (기존 금융 포트폴리오 + 가상화폐)
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            (금융 포트폴리오 {combined.portfolio_weight_pct?.toFixed(1)}% + 가상화폐 {combined.crypto_weight_pct?.toFixed(1)}%)
          </span>
        </div>

        {/* 4 KPI Cards Grid */}
        <div className="kpi-grid" style={{ marginTop: '16px', marginBottom: '16px' }}>
          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">💎 통합 총 평가금액 (전체 자산)</div>
            <div className="kpi-value" style={{ color: 'var(--accent-primary)', fontSize: '1.45rem' }}>
              {formatKRW(combined.total_eval)}
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">🛒 통합 총 매입금액 (원금 합계)</div>
            <div className="kpi-value" style={{ fontSize: '1.45rem' }}>
              {formatKRW(combined.total_buy)}
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">📈 통합 총 평가손익 (수익률)</div>
            <div className="kpi-value" style={{ color: isCombinedProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontSize: '1.45rem' }}>
              {isCombinedProfit ? '+' : ''}{formatKRW(combined.total_profit)}
              <span style={{ fontSize: '0.95rem', marginLeft: '6px', fontWeight: 600 }}>
                ({formatPercent(combined.total_profit_pct)})
              </span>
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">⚖️ 전체 자산 배분 비중</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700 }}>
                <span style={{ color: 'var(--accent-primary)' }}>🏦 금융 {combined.portfolio_weight_pct?.toFixed(1)}%</span>
                <span style={{ color: '#F59E0B' }}>🪙 코인 {combined.crypto_weight_pct?.toFixed(1)}%</span>
              </div>
              <div style={{ height: '10px', background: 'rgba(255,255,255,0.08)', borderRadius: '5px', overflow: 'hidden', display: 'flex' }}>
                <div style={{ width: `${combined.portfolio_weight_pct || 0}%`, background: 'var(--accent-primary)' }} title={`금융 포트폴리오: ${combined.portfolio_weight_pct?.toFixed(1)}%`} />
                <div style={{ width: `${btc.weight_in_combined_pct || 0}%`, background: '#F59E0B' }} title={`비트코인: ${btc.weight_in_combined_pct?.toFixed(1)}%`} />
                <div style={{ width: `${eth.weight_in_combined_pct || 0}%`, background: '#8B5CF6' }} title={`이더리움: ${eth.weight_in_combined_pct?.toFixed(1)}%`} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Crypto Cards (BTC & ETH) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
        {/* BTC Card */}
        <div className="section-card" style={{ border: '1px solid rgba(245, 158, 11, 0.3)', position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ width: '38px', height: '38px', borderRadius: '50%', background: 'rgba(245, 158, 11, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.3rem' }}>
                🪙
              </div>
              <div>
                <div style={{ fontWeight: 800, fontSize: '1.15rem' }}>비트코인 (BTC)</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>출처: {btc.source || '업비트 실시간'}</div>
              </div>
            </div>

            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                {formatKRW(btc.current_price)}
              </div>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '2px', fontSize: '0.82rem', fontWeight: 700, color: (btc.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                {(btc.change_24h_pct || 0) >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                {(btc.change_24h_pct || 0) >= 0 ? '+' : ''}{btc.change_24h_pct?.toFixed(2)}%
              </div>
            </div>
          </div>

          <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-md)', display: 'flex', flexDirection: 'column', gap: '10px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>보유 수량</span>
              <strong style={{ fontSize: '0.95rem' }}>{btc.quantity ? Number(btc.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} BTC</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>매수 평단가</span>
              <strong style={{ fontSize: '0.95rem' }}>{formatKRW(btc.avg_price)}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem', paddingTop: '6px', borderTop: '1px dashed var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>총 매입금액</span>
              <strong style={{ fontSize: '0.95rem' }}>{formatKRW(btc.buy_amount)}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>현재 평가금액</span>
              <strong style={{ fontSize: '1.05rem', color: 'var(--accent-primary)' }}>{formatKRW(btc.eval_amount)}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem', paddingTop: '6px', borderTop: '1px solid var(--border-color)' }}>
              <span style={{ fontWeight: 600 }}>평가 손익 (수익률)</span>
              <strong style={{ fontSize: '1rem', color: (btc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                {(btc.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(btc.profit_krw)} ({formatPercent(btc.profit_pct)})
              </strong>
            </div>
          </div>
        </div>

        {/* ETH Card */}
        <div className="section-card" style={{ border: '1px solid rgba(139, 92, 246, 0.3)', position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ width: '38px', height: '38px', borderRadius: '50%', background: 'rgba(139, 92, 246, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.3rem' }}>
                💎
              </div>
              <div>
                <div style={{ fontWeight: 800, fontSize: '1.15rem' }}>이더리움 (ETH)</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>출처: {eth.source || '업비트 실시간'}</div>
              </div>
            </div>

            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                {formatKRW(eth.current_price)}
              </div>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '2px', fontSize: '0.82rem', fontWeight: 700, color: (eth.change_24h_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                {(eth.change_24h_pct || 0) >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                {(eth.change_24h_pct || 0) >= 0 ? '+' : ''}{eth.change_24h_pct?.toFixed(2)}%
              </div>
            </div>
          </div>

          <div className="background-surface" style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-md)', display: 'flex', flexDirection: 'column', gap: '10px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>보유 수량</span>
              <strong style={{ fontSize: '0.95rem' }}>{eth.quantity ? Number(eth.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} ETH</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>매수 평단가</span>
              <strong style={{ fontSize: '0.95rem' }}>{formatKRW(eth.avg_price)}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem', paddingTop: '6px', borderTop: '1px dashed var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>총 매입금액</span>
              <strong style={{ fontSize: '0.95rem' }}>{formatKRW(eth.buy_amount)}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>현재 평가금액</span>
              <strong style={{ fontSize: '1.05rem', color: 'var(--accent-primary)' }}>{formatKRW(eth.eval_amount)}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem', paddingTop: '6px', borderTop: '1px solid var(--border-color)' }}>
              <span style={{ fontWeight: 600 }}>평가 손익 (수익률)</span>
              <strong style={{ fontSize: '1rem', color: (eth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                {(eth.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(eth.profit_krw)} ({formatPercent(eth.profit_pct)})
              </strong>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Detailed Comparison Table */}
      <div className="section-card">
        <div className="section-title">
          <span>📊 자산군별 세부 비교 및 비중 현황</span>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>자산 구분</th>
                <th>보유량 / 세부내용</th>
                <th>총 매입금액(원)</th>
                <th>현재 평가금액(원)</th>
                <th>평가 손익(원)</th>
                <th>수익률(%)</th>
                <th>통합 자산 비중(%)</th>
              </tr>
            </thead>
            <tbody>
              {/* 1) Financial Portfolio Row */}
              <tr>
                <td style={{ fontWeight: 700 }}>
                  🏦 기존 금융 포트폴리오
                </td>
                <td style={{ color: 'var(--text-secondary)' }}>주식/ETF/금/예수금</td>
                <td>{formatKRW(portfolioSummary.total_buy)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(portfolioSummary.total_eval)}</td>
                <td style={{ color: isPortfolioProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {isPortfolioProfit ? '+' : ''}{formatKRW(portfolioSummary.total_profit)}
                </td>
                <td style={{ color: isPortfolioProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(portfolioSummary.total_profit_pct)}
                </td>
                <td style={{ fontWeight: 700, color: 'var(--accent-primary)' }}>
                  {portfolioSummary.weight_pct?.toFixed(2)}%
                </td>
              </tr>

              {/* 2) Bitcoin Row */}
              <tr>
                <td style={{ fontWeight: 700, color: '#F59E0B' }}>
                  🪙 비트코인 (BTC)
                </td>
                <td>{btc.quantity ? Number(btc.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} BTC</td>
                <td>{formatKRW(btc.buy_amount)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(btc.eval_amount)}</td>
                <td style={{ color: (btc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {(btc.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(btc.profit_krw)}
                </td>
                <td style={{ color: (btc.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(btc.profit_pct)}
                </td>
                <td style={{ fontWeight: 700 }}>
                  {btc.weight_in_combined_pct?.toFixed(2)}%
                </td>
              </tr>

              {/* 3) Ethereum Row */}
              <tr>
                <td style={{ fontWeight: 700, color: '#8B5CF6' }}>
                  💎 이더리움 (ETH)
                </td>
                <td>{eth.quantity ? Number(eth.quantity).toFixed(8).replace(/\.?0+$/, '') : '0'} ETH</td>
                <td>{formatKRW(eth.buy_amount)}</td>
                <td style={{ fontWeight: 600 }}>{formatKRW(eth.eval_amount)}</td>
                <td style={{ color: (eth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {(eth.profit_krw || 0) >= 0 ? '+' : ''}{formatKRW(eth.profit_krw)}
                </td>
                <td style={{ color: (eth.profit_krw || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(eth.profit_pct)}
                </td>
                <td style={{ fontWeight: 700 }}>
                  {eth.weight_in_combined_pct?.toFixed(2)}%
                </td>
              </tr>

              {/* 4) Crypto Subtotal Row */}
              <tr style={{ background: 'rgba(245, 158, 11, 0.04)', fontStyle: 'italic' }}>
                <td style={{ fontWeight: 700, paddingLeft: '24px' }}>
                  ↳ 🪙 가상화폐 소계
                </td>
                <td>BTC + ETH 합계</td>
                <td>{formatKRW(cryptoTotal.total_buy)}</td>
                <td>{formatKRW(cryptoTotal.total_eval)}</td>
                <td style={{ color: isCryptoProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {isCryptoProfit ? '+' : ''}{formatKRW(cryptoTotal.total_profit)}
                </td>
                <td style={{ color: isCryptoProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                  {formatPercent(cryptoTotal.total_profit_pct)}
                </td>
                <td style={{ fontWeight: 700, color: '#F59E0B' }}>
                  {combined.crypto_weight_pct?.toFixed(2)}%
                </td>
              </tr>

              {/* 5) Total Combined Row */}
              <tr className="total-row" style={{ fontSize: '1rem' }}>
                <td style={{ fontWeight: 800 }}>🌟 통합 전체 합계</td>
                <td>전체 자산 종합</td>
                <td>{formatKRW(combined.total_buy)}</td>
                <td style={{ fontWeight: 800, color: 'var(--accent-primary)' }}>{formatKRW(combined.total_eval)}</td>
                <td style={{ color: isCombinedProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {isCombinedProfit ? '+' : ''}{formatKRW(combined.total_profit)}
                </td>
                <td style={{ color: isCombinedProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {formatPercent(combined.total_profit_pct)}
                </td>
                <td style={{ fontWeight: 800 }}>100.00%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit Crypto Modal */}
      <EditCryptoModal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        initialHoldings={cryptoAssets}
        onSave={handleSaveHoldings}
      />
    </div>
  );
}
