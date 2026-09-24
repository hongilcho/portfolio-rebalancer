import React, { useState, useEffect, useMemo } from 'react';
import { 
  Coins, TrendingUp, TrendingDown, RefreshCw, Edit3, 
  ArrowUpRight, ArrowDownRight, PieChart, ShieldCheck, Sparkles, User, Users 
} from 'lucide-react';
import { api } from '../../utils/api';
import { formatKRW, formatPercent } from '../../utils/formatters';
import DonutChart from '../common/DonutChart';
import EditCryptoModal from './EditCryptoModal';

export default function CryptoTab({ 
  currentPortfolioId = 'default',
  portfolioName = '금융 포트폴리오'
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [chartView, setChartView] = useState('both'); // 'both' | 'owner' | 'coin'

  const byOwner = data?.by_owner || {};
  const hongil = byOwner['홍일'] || { assets: [], total_buy: 0, total_eval: 0, total_profit: 0, total_profit_pct: 0, share_pct: 0 };
  const yoona = byOwner['윤아'] || { assets: [], total_buy: 0, total_eval: 0, total_profit: 0, total_profit_pct: 0, share_pct: 0 };

  const hongilBtc = hongil.assets?.find(a => a.symbol === 'BTC') || {};
  const hongilEth = hongil.assets?.find(a => a.symbol === 'ETH') || {};

  const yoonaBtc = yoona.assets?.find(a => a.symbol === 'BTC') || {};
  const yoonaEth = yoona.assets?.find(a => a.symbol === 'ETH') || {};

  const cryptoAssetsCombined = data?.crypto_assets_combined || [];
  const btcComb = cryptoAssetsCombined.find(a => a.symbol === 'BTC') || {};
  const ethComb = cryptoAssetsCombined.find(a => a.symbol === 'ETH') || {};

  const cryptoTotal = data?.crypto_total || {};
  const portfolioSummary = data?.portfolio_summary || {};
  const combined = data?.combined_summary || {};

  // 홍일 vs 윤아 지분 비중 도넛 데이터
  const ownerDonutData = useMemo(() => {
    return [
      {
        label: '👨 홍일 계정',
        value: Number(hongil.total_eval) || 0,
        color: '#0EA5E9'
      },
      {
        label: '👩 윤아 계정',
        value: Number(yoona.total_eval) || 0,
        color: '#EC4899'
      }
    ].filter(item => item.value > 0);
  }, [hongil.total_eval, yoona.total_eval]);

  // 코인별(BTC vs ETH) 비중 도넛 데이터
  const coinDonutData = useMemo(() => {
    const symbolColors = {
      'BTC': '#F59E0B',
      'ETH': '#8B5CF6'
    };
    return (cryptoAssetsCombined || [])
      .map(c => ({
        label: `${c.name || c.symbol} (${c.symbol})`,
        value: Number(c.eval_amount) || 0,
        color: symbolColors[c.symbol] || '#06B6D4'
      }))
      .filter(c => c.value > 0);
  }, [cryptoAssetsCombined]);

  const loadCryptoSummary = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      const res = await api.getCryptoSummary(currentPortfolioId);
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
  }, [currentPortfolioId]);

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

  const isCombinedProfit = (combined.total_profit || 0) >= 0;
  const isCryptoProfit = (cryptoTotal.total_profit || 0) >= 0;
  const isPortfolioProfit = (portfolioSummary.total_profit || 0) >= 0;
  const isHongilProfit = (hongil.total_profit || 0) >= 0;
  const isYoonaProfit = (yoona.total_profit || 0) >= 0;

  const currentPortName = portfolioSummary.portfolio_name || portfolioName || '금융 포트폴리오';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Action Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Coins size={24} color="#F59E0B" />
            가상화폐 자산 포트폴리오 (업비트)
          </h2>
          <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            홍일 & 윤아의 비트코인 및 이더리움 자산을 개별 관리하고 종합 분석합니다.
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

      {/* 1. Standalone Crypto Portfolio Overview (가상화폐 전체 총계) */}
      <div className="section-card" style={{ background: 'linear-gradient(145deg, var(--bg-card), rgba(245, 158, 11, 0.04))', border: '1px solid rgba(245, 158, 11, 0.25)' }}>
        <div className="section-title" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#F59E0B', fontWeight: 800 }}>
            <Sparkles size={18} />
            🪙 가상화폐 자산 종합 총계 (업비트)
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            홍일 & 윤아 합산 총 평가액: {formatKRW(cryptoTotal.total_eval)}
          </span>
        </div>

        {/* 4 KPI Cards Grid */}
        <div className="kpi-grid" style={{ marginTop: '16px', marginBottom: '16px' }}>
          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">💎 가상화폐 총 평가금액</div>
            <div className="kpi-value" style={{ color: 'var(--accent-primary)', fontSize: '1.45rem' }}>
              {formatKRW(cryptoTotal.total_eval)}
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">🛒 가상화폐 총 매입금액 (원금)</div>
            <div className="kpi-value" style={{ fontSize: '1.45rem' }}>
              {formatKRW(cryptoTotal.total_buy)}
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">📈 가상화폐 총 평가손익 (수익률)</div>
            <div className="kpi-value" style={{ color: isCryptoProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontSize: '1.45rem' }}>
              {isCryptoProfit ? '+' : ''}{formatKRW(cryptoTotal.total_profit)}
              <span style={{ fontSize: '0.95rem', marginLeft: '6px', fontWeight: 600 }}>
                ({formatPercent(cryptoTotal.total_profit_pct)})
              </span>
            </div>
          </div>

          <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
            <div className="kpi-title">⚖️ 홍일 vs 윤아 지분율 비중</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', fontWeight: 700 }}>
                <span style={{ color: '#0EA5E9' }}>👨 홍일 {hongil.share_pct?.toFixed(1)}%</span>
                <span style={{ color: '#EC4899' }}>👩 윤아 {yoona.share_pct?.toFixed(1)}%</span>
              </div>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                <div style={{ width: `${hongil.share_pct || 0}%`, background: '#0EA5E9' }} title={`홍일: ${hongil.share_pct?.toFixed(1)}%`} />
                <div style={{ width: `${yoona.share_pct || 0}%`, background: '#EC4899' }} title={`윤아: ${yoona.share_pct?.toFixed(1)}%`} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                <span>{formatKRW(hongil.total_eval)}</span>
                <span>{formatKRW(yoona.total_eval)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Interactive Donut Charts Section (지분율 / 코인별 비중) */}
      <div className="section-card">
        <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PieChart size={18} color="#F59E0B" />
            가상화폐 비중 분석 (도넛 차트)
          </span>

          <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-surface)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('both')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'both' ? '#F59E0B' : 'transparent',
                color: chartView === 'both' ? '#000' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              지분 & 코인 듀얼
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('owner')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'owner' ? '#F59E0B' : 'transparent',
                color: chartView === 'owner' ? '#000' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              홍일 vs 윤아 지분
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('coin')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'coin' ? '#F59E0B' : 'transparent',
                color: chartView === 'coin' ? '#000' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              코인별 비중 (BTC/ETH)
            </button>
          </div>
        </div>

        {/* Charts Container */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: chartView === 'both' ? 'repeat(auto-fit, minmax(360px, 1fr))' : '1fr', 
          gap: '24px',
          marginTop: '12px' 
        }}>
          {(chartView === 'both' || chartView === 'owner') && (
            <div style={{ 
              background: 'var(--bg-surface)', 
              padding: '16px 20px', 
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)' 
            }}>
              <DonutChart
                title="👥 홍일 vs 윤아 지분 비중"
                data={ownerDonutData}
                centerLabel="가상화폐 총 평가액"
                centerValue={formatKRW(cryptoTotal.total_eval)}
                size={230}
              />
            </div>
          )}

          {(chartView === 'both' || chartView === 'coin') && (
            <div style={{ 
              background: 'var(--bg-surface)', 
              padding: '16px 20px', 
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)' 
            }}>
              <DonutChart
                title="🪙 비트코인 vs 이더리움 비중"
                data={coinDonutData}
                centerLabel="코인 총 평가액"
                centerValue={formatKRW(cryptoTotal.total_eval)}
                size={230}
              />
            </div>
          )}
        </div>
      </div>

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

      {/* Edit Crypto Modal */}
      <EditCryptoModal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        byOwner={byOwner}
        onSave={handleSaveHoldings}
      />
    </div>
  );
}
