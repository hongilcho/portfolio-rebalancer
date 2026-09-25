/**
 * 전체 자산 종합 요약 컴포넌트 (AllPortfoliosOverview.jsx)
 * ========================================================
 * 등록된 모든 금융 포트폴리오와 가상자산(암호화폐)을 통합하여
 * 총 순자산(Grand Total), 포트폴리오별 비중, 통합 종목별 보유 현황을 보여줍니다.
 * 
 * 주요 기능:
 * - 전체 종합 순자산, 총 투자원금, 총 평가손익 및 수익률 KPI
 * - 가상자산(비트코인/이더리움) 포함/제외 동적 토글
 * - 포트폴리오별 배분 및 대분류 자산군별 듀얼 도넛 차트
 * - 복수 포트폴리오 통합 종목 현황(가중평균 매입단가 및 포트폴리오 태그 표시)
 * - 개별 포트폴리오 바로가기 네비게이션
 * 
 * @param {Function} props.onSelectPortfolio - 특정 포트폴리오 선택 시 해당 화면으로 전환하는 콜백
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { 
  Sparkles, RefreshCw, TrendingUp, 
  Layers, ArrowRight, CheckSquare, Square, PieChart
} from 'lucide-react';
import { api } from '../../utils/api';
import { formatKRW, formatUSD, formatPercent } from '../../utils/formatters';
import DonutChart from '../common/DonutChart';

let _overviewCache = null;
try {
  const saved = sessionStorage.getItem('portfolio_overview_cache');
  if (saved) _overviewCache = JSON.parse(saved);
} catch {}

export default function AllPortfoliosOverview({ onSelectPortfolio, currencyMode = 'KRW' }) {
  const [data, setData] = useState(() => _overviewCache);
  const [loading, setLoading] = useState(() => !_overviewCache);
  const [refreshing, setRefreshing] = useState(false);
  const [includeCrypto, setIncludeCrypto] = useState(true);
  const [error, setError] = useState('');

  const [chartView, setChartView] = useState('dual'); // 'dual' | 'portfolios' | 'assetClasses'

  const portfolioColors = useMemo(() => ['#6366F1', '#10B981', '#F59E0B', '#EC4899', '#8B5CF6', '#3B82F6'], []);

  const grand = data?.grand_total || {};
  const portfolios = data?.portfolios || [];
  const crypto = data?.crypto || null;
  const aggregatedAssets = data?.aggregated_assets || [];

  // 포트폴리오별 구성 비중 도넛 데이터
  const portfolioDonutData = useMemo(() => {
    const list = (data?.portfolios || []).map((p, idx) => ({
      label: p.name,
      value: Number(p.total_eval) || 0,
      color: portfolioColors[idx % portfolioColors.length]
    }));

    if (includeCrypto && crypto && (Number(crypto.total_eval) || 0) > 0) {
      list.push({
        label: '🪙 가상화폐 (업비트)',
        value: Number(crypto.total_eval),
        color: '#F59E0B'
      });
    }

    return list.filter(item => item.value > 0).sort((a, b) => b.value - a.value);
  }, [data?.portfolios, includeCrypto, crypto, portfolioColors]);

  // 자산군(Asset Class)별 비중 도넛 데이터 (예수금/현금 제외, 순수 자산군)
  const assetClassDonutData = useMemo(() => {
    const classMap = {
      'equity': { label: '📈 주식', value: 0, color: '#3B82F6' },
      'bonds': { label: '📜 채권', value: 0, color: '#8B5CF6' },
      'gold_commodities': { label: '🥇 대체투자', value: 0, color: '#EAB308' },
      'deposits': { label: '🏦 예금', value: 0, color: '#10B981' },
      'crypto': { label: '🪙 가상화폐', value: 0, color: '#F97316' },
    };

    (data?.aggregated_assets || []).forEach(item => {
      const evalAmt = Number(item.total_eval_amount) || 0;
      if (evalAmt <= 0) return;

      const name = (item.name || '').toLowerCase();
      const ticker = (item.ticker || '').toUpperCase();
      const market = (item.market || '').toUpperCase();
      const assetType = (item.asset_type || '').toUpperCase();

      const isDep = item.is_deposit || 
                    assetType === 'DEPOSIT' || 
                    ticker.startsWith('DEP') || 
                    name.includes('예금') || 
                    name.includes('적금') || 
                    name.includes('새마을') || 
                    name.includes('금고');

      if (isDep) {
        classMap['deposits'].value += evalAmt;
      } else if (assetType === 'CRYPTO' || market === 'CRYPTO') {
        classMap['crypto'].value += evalAmt;
      } else if (name.includes('금99') || name.includes('금 99') || name.includes('원자재') || name.includes('gold') || ticker === 'PDBC' || ticker === 'M04020000') {
        classMap['gold_commodities'].value += evalAmt;
      } else if (name.includes('국채') || name.includes('채권') || name.includes('bond') || ticker === '0085P0' || ticker === '476760') {
        classMap['bonds'].value += evalAmt;
      } else {
        // 국내/해외 구분 없이 모두 '주식'
        classMap['equity'].value += evalAmt;
      }
    });

    return Object.values(classMap)
      .filter(item => item.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [data?.aggregated_assets]);

  const loadOverview = useCallback(async (isRefresh = false, cryptoToggle = includeCrypto) => {
    if (isRefresh) setRefreshing(true);
    else if (!_overviewCache) setLoading(true);
    setError('');

    try {
      const res = await api.getPortfoliosOverview(cryptoToggle, isRefresh);
      _overviewCache = res;
      setData(res);
      try {
        sessionStorage.setItem('portfolio_overview_cache', JSON.stringify(res));
      } catch {}
    } catch (err) {
      console.error('Failed to load portfolios overview:', err);
      setError(err.message || '전체 자산 종합 요약을 불러오는 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [includeCrypto]);

  useEffect(() => {
    loadOverview(false, includeCrypto);
  }, [loadOverview, includeCrypto]);

  const handleToggleCrypto = () => {
    const nextVal = !includeCrypto;
    setIncludeCrypto(nextVal);
  };

  if (loading && !data) {
    return (
      <div className="section-card" style={{ textAlign: 'center', padding: '60px 20px' }}>
        <RefreshCw size={28} className="animate-spin" style={{ margin: '0 auto 12px', color: 'var(--accent-primary)' }} />
        <p style={{ color: 'var(--text-secondary)' }}>모든 포트폴리오 및 자산 종합 데이터를 불러오는 중입니다...</p>
      </div>
    );
  }

  const isGrandProfit = (grand.total_profit || 0) >= 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
      {/* Top Header & Toggle Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={24} color="var(--accent-primary)" />
            가문 전체 자산 종합 요약
          </h2>
          <span style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
            모든 독립 포트폴리오와 가상화폐를 합산한 전체 순자산 및 종목별 통합 집계 현황입니다.
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Crypto Toggle Button */}
          <button 
            className="btn btn-secondary btn-sm"
            onClick={handleToggleCrypto}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px',
              borderColor: includeCrypto ? 'var(--accent-primary)' : 'var(--border-color)',
              background: includeCrypto ? 'rgba(99, 102, 241, 0.1)' : 'var(--bg-surface)'
            }}
          >
            {includeCrypto ? (
              <CheckSquare size={16} color="var(--accent-primary)" />
            ) : (
              <Square size={16} color="var(--text-muted)" />
            )}
            <span style={{ fontWeight: 600, color: includeCrypto ? 'var(--accent-primary)' : 'inherit' }}>
              가상화폐(비트코인/이더리움) 자산 포함
            </span>
          </button>

          <button 
            className="btn btn-secondary btn-sm"
            onClick={() => loadOverview(true, includeCrypto)}
            disabled={refreshing}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? '조회 중...' : '새로고침'}
          </button>
        </div>
      </div>

      {error && (
        <div className="alert-banner alert-danger">
          <span>⚠️ {error}</span>
        </div>
      )}

      {/* 1. Grand Total KPI Grid */}
      <div className="section-card" style={{ background: 'linear-gradient(145deg, var(--bg-card), rgba(99, 102, 241, 0.05))', border: '1px solid rgba(99, 102, 241, 0.25)' }}>
        <div className="section-title" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-primary)', fontWeight: 800 }}>
            <Layers size={18} />
            🌟 가문 전체 통합 자산 요약
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            (포트폴리오 {portfolios.length}개{includeCrypto && crypto ? ' + 가상화폐' : ''})
          </span>
        </div>

        {currencyMode === 'USD' ? (
          <div style={{ marginTop: '16px', marginBottom: '16px' }}>
            <div className="dual-currency-kpi-grid">
              {/* 1) 🇺🇸 가문 외화 자산 종합 (USD) */}
              <div className="dual-kpi-card usd-card">
                <div className="dual-kpi-header">
                  <div className="dual-kpi-title">
                    <span className="badge badge-accent">🇺🇸 가문 외화 자산 종합 (USD)</span>
                    <span className="dual-kpi-subtitle">미국 상장 ETF/주식 & 외화 예수금 통합</span>
                  </div>
                  <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: 'var(--accent-primary)', fontSize: '0.74rem' }}>
                    외화 순자산 {formatUSD(grand?.usd_summary?.total_eval_usd)}
                  </span>
                </div>
                <div className="dual-kpi-main">
                  <div className="dual-kpi-main-label">외화 총 평가금액</div>
                  <div className="dual-kpi-main-value" style={{ color: 'var(--accent-primary)' }}>
                    {formatUSD(grand?.usd_summary?.stock_eval_usd)}
                  </div>
                  <div className="dual-kpi-sub-row">
                    <span className="dual-kpi-sub-label">외화 평가손익:</span>
                    <span className={`dual-kpi-sub-value ${(grand?.usd_summary?.stock_profit_usd || 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {formatUSD(grand?.usd_summary?.stock_profit_usd, true)} ({formatPercent(grand?.usd_summary?.stock_return_usd)})
                    </span>
                  </div>
                </div>
                <div className="dual-kpi-footer">
                  <div className="dual-kpi-footer-item">
                    <span>외화 투자원금</span>
                    <strong>{formatUSD(grand?.usd_summary?.stock_buy_usd)}</strong>
                  </div>
                  <div className="dual-kpi-footer-divider" />
                  <div className="dual-kpi-footer-item">
                    <span>외화 예수금</span>
                    <strong style={{ color: 'var(--accent-primary)' }}>{formatUSD(grand?.usd_summary?.cash_usd)}</strong>
                  </div>
                </div>
              </div>

              {/* 2) 🇰🇷 가문 원화 자산 종합 (KRW) */}
              <div className="dual-kpi-card krw-card">
                <div className="dual-kpi-header">
                  <div className="dual-kpi-title">
                    <span className="badge badge-safe">🇰🇷 가문 원화 자산 종합 (KRW)</span>
                    <span className="dual-kpi-subtitle">국내 증시·채권·금·예금·가상화폐 & 원화 예수금</span>
                  </div>
                  <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-safe)', fontSize: '0.74rem' }}>
                    원화 순자산 {formatKRW(grand?.krw_summary?.total_eval_krw)}
                  </span>
                </div>
                <div className="dual-kpi-main">
                  <div className="dual-kpi-main-label">원화 총 평가금액</div>
                  <div className="dual-kpi-main-value" style={{ color: 'var(--color-safe)' }}>
                    {formatKRW(grand?.krw_summary?.stock_eval_krw)}
                  </div>
                  <div className="dual-kpi-sub-row">
                    <span className="dual-kpi-sub-label">원화 평가손익:</span>
                    <span className={`dual-kpi-sub-value ${(grand?.krw_summary?.stock_profit_krw || 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {formatKRW(grand?.krw_summary?.stock_profit_krw, true)} ({formatPercent(grand?.krw_summary?.stock_return_krw)})
                    </span>
                  </div>
                </div>
                <div className="dual-kpi-footer">
                  <div className="dual-kpi-footer-item">
                    <span>원화 투자원금</span>
                    <strong>{formatKRW(grand?.krw_summary?.stock_buy_krw)}</strong>
                  </div>
                  <div className="dual-kpi-footer-divider" />
                  <div className="dual-kpi-footer-item">
                    <span>원화 예수금</span>
                    <strong style={{ color: 'var(--color-safe)' }}>{formatKRW(grand?.krw_summary?.cash_krw)}</strong>
                  </div>
                </div>
              </div>
            </div>

            {/* Asset Distribution Bar */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px 16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', marginTop: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>⚖️ 자산 배분 비중 현황</span>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>통합 전체 환산 순자산: {formatKRW(grand.total_eval)}</span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '0.8rem', fontWeight: 700, marginBottom: '6px' }}>
                {portfolios.map((p, idx) => (
                  <span key={p.id} style={{ color: portfolioColors[idx % portfolioColors.length] }}>
                    💼 {p.name} {p.weight_pct?.toFixed(1)}%
                  </span>
                ))}
                {includeCrypto && crypto && (
                  <span style={{ color: '#F59E0B' }}>
                    🪙 가상화폐 {crypto.weight_pct?.toFixed(1)}%
                  </span>
                )}
              </div>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                {portfolios.map((p, idx) => (
                  <div 
                    key={p.id}
                    style={{ width: `${p.weight_pct || 0}%`, background: portfolioColors[idx % portfolioColors.length] }} 
                    title={`${p.name}: ${p.weight_pct?.toFixed(1)}%`} 
                  />
                ))}
                {includeCrypto && crypto && (
                  <div 
                    style={{ width: `${crypto.weight_pct || 0}%`, background: '#F59E0B' }} 
                    title={`가상화폐: ${crypto.weight_pct?.toFixed(1)}%`} 
                  />
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="kpi-grid" style={{ marginTop: '16px', marginBottom: '16px' }}>
            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">💎 통합 총 평가금액 (전체 순자산)</div>
              <div className="kpi-value" style={{ color: 'var(--accent-primary)', fontSize: '1.5rem' }}>
                {formatKRW(grand.total_eval)}
              </div>
            </div>

            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">🛒 통합 총 매입금액 (원금 합계)</div>
              <div className="kpi-value" style={{ fontSize: '1.5rem' }}>
                {formatKRW(grand.total_buy)}
              </div>
            </div>

            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">📈 통합 총 평가손익 (수익률)</div>
              <div className="kpi-value" style={{ color: isGrandProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontSize: '1.5rem' }}>
                {isGrandProfit ? '+' : ''}{formatKRW(grand.total_profit)}
                <span style={{ fontSize: '0.95rem', marginLeft: '6px', fontWeight: 600 }}>
                  ({formatPercent(grand.total_profit_pct)})
                </span>
              </div>
            </div>

            <div className="kpi-card" style={{ background: 'var(--bg-surface)' }}>
              <div className="kpi-title">⚖️ 자산 배분 비중 현황</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '0.8rem', fontWeight: 700 }}>
                  {portfolios.map((p, idx) => (
                    <span key={p.id} style={{ color: portfolioColors[idx % portfolioColors.length] }}>
                      💼 {p.name} {p.weight_pct?.toFixed(1)}%
                    </span>
                  ))}
                  {includeCrypto && crypto && (
                    <span style={{ color: '#F59E0B' }}>
                      🪙 가상화폐 {crypto.weight_pct?.toFixed(1)}%
                    </span>
                  )}
                </div>
                <div style={{ height: '10px', background: 'rgba(255,255,255,0.08)', borderRadius: '5px', overflow: 'hidden', display: 'flex' }}>
                  {portfolios.map((p, idx) => (
                    <div 
                      key={p.id}
                      style={{ width: `${p.weight_pct || 0}%`, background: portfolioColors[idx % portfolioColors.length] }} 
                      title={`${p.name}: ${p.weight_pct?.toFixed(1)}%`} 
                    />
                  ))}
                  {includeCrypto && crypto && (
                    <div 
                      style={{ width: `${crypto.weight_pct || 0}%`, background: '#F59E0B' }} 
                      title={`가상화폐: ${crypto.weight_pct?.toFixed(1)}%`} 
                    />
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 2. Interactive Donut Charts Section (포트폴리오별 / 자산군별 비중) */}
      <div className="section-card">
        <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PieChart size={18} color="var(--accent-primary)" />
            통합 자산 구성 비중 분석 (도넛 차트)
          </span>

          <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-surface)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('dual')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'dual' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'dual' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              포트폴리오 & 자산군 듀얼
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('portfolios')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'portfolios' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'portfolios' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              포트폴리오별 비중
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('assetClasses')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'assetClasses' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'assetClasses' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              자산군 대분류별 비중
            </button>
          </div>
        </div>

        {/* Charts Grid Container */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: chartView === 'dual' ? 'repeat(auto-fit, minmax(360px, 1fr))' : '1fr', 
          gap: '24px',
          marginTop: '12px' 
        }}>
          {(chartView === 'dual' || chartView === 'portfolios') && (
            <div style={{ 
              background: 'var(--bg-surface)', 
              padding: '16px 20px', 
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)' 
            }}>
              <DonutChart
                title="💼 포트폴리오별 순자산 구성 비중"
                data={portfolioDonutData}
                centerLabel="전체 순자산"
                centerValue={formatKRW(grand.total_eval)}
                size={230}
              />
            </div>
          )}

          {(chartView === 'dual' || chartView === 'assetClasses') && (
            <div style={{ 
              background: 'var(--bg-surface)', 
              padding: '16px 20px', 
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)' 
            }}>
              <DonutChart
                title="🌐 자산군 대분류별 자산 비중"
                data={assetClassDonutData}
                centerLabel="전체 순자산"
                centerValue={formatKRW(grand.total_eval)}
                size={230}
              />
            </div>
          )}
        </div>
      </div>

      {/* 3. Portfolios & Asset Class Overview Table */}
      <div className="section-card">
        <div className="section-title">
          <span>📊 포트폴리오 및 자산군별 비교 현황</span>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>포트폴리오 / 자산 구분</th>
                <th>운용 전략 (설명/메모)</th>
                <th>총 매입금액(원)</th>
                <th>현재 평가금액(원)</th>
                <th>평가 손익(원)</th>
                <th>수익률(%)</th>
                <th>보유 계좌/종목수</th>
                <th>전체 자산 비중(%)</th>
                <th>바로가기</th>
              </tr>
            </thead>
            <tbody>
              {portfolios.map((p, idx) => {
                const isPProfit = (p.total_profit || 0) >= 0;
                return (
                  <tr key={p.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: portfolioColors[idx % portfolioColors.length] }} />
                        <strong style={{ fontSize: '0.96rem' }}>{p.name}</strong>
                        {p.is_default && (
                          <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>기본</span>
                        )}
                      </div>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      {p.description || '-'}
                    </td>
                    <td>{formatKRW(p.total_buy)}</td>
                    <td style={{ fontWeight: 700 }}>{formatKRW(p.total_eval)}</td>
                    <td style={{ color: isPProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                      {isPProfit ? '+' : ''}{formatKRW(p.total_profit)}
                    </td>
                    <td style={{ color: isPProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                      {formatPercent(p.total_profit_pct)}
                    </td>
                    <td style={{ color: 'var(--text-secondary)' }}>
                      계좌 {p.account_count}개 / 종목 {p.asset_count}개
                    </td>
                    <td style={{ fontWeight: 700, color: portfolioColors[idx % portfolioColors.length] }}>
                      {p.weight_pct?.toFixed(2)}%
                    </td>
                    <td>
                      <button 
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectPortfolio(p.id)}
                        style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '4px 8px', fontSize: '0.78rem' }}
                      >
                        이동 <ArrowRight size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}

              {/* Crypto Row if included */}
              {includeCrypto && crypto && (
                <tr style={{ background: 'rgba(245, 158, 11, 0.04)' }}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#F59E0B' }} />
                      <strong style={{ fontSize: '0.96rem', color: '#F59E0B' }}>🪙 가상화폐 자산</strong>
                    </div>
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                    비트코인(BTC) 및 이더리움(ETH)
                  </td>
                  <td>{formatKRW(crypto.total_buy)}</td>
                  <td style={{ fontWeight: 700 }}>{formatKRW(crypto.total_eval)}</td>
                  <td style={{ color: (crypto.total_profit || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                    {(crypto.total_profit || 0) >= 0 ? '+' : ''}{formatKRW(crypto.total_profit)}
                  </td>
                  <td style={{ color: (crypto.total_profit || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                    {formatPercent(crypto.total_profit_pct)}
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>
                    코인 {crypto.assets?.length || 2}종
                  </td>
                  <td style={{ fontWeight: 700, color: '#F59E0B' }}>
                    {crypto.weight_pct?.toFixed(2)}%
                  </td>
                  <td>
                    <button 
                      className="btn btn-secondary btn-sm"
                      onClick={() => onSelectPortfolio('crypto')}
                      style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '4px 8px', fontSize: '0.78rem' }}
                    >
                      이동 <ArrowRight size={12} />
                    </button>
                  </td>
                </tr>
              )}

              {/* Total Summary Row */}
              <tr className="total-row" style={{ fontSize: '1rem' }}>
                <td style={{ fontWeight: 800 }}>🌟 통합 전체 합계</td>
                <td>가문 전체 자산 종합</td>
                <td>{formatKRW(grand.total_buy)}</td>
                <td style={{ fontWeight: 800, color: 'var(--accent-primary)' }}>{formatKRW(grand.total_eval)}</td>
                <td style={{ color: isGrandProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {isGrandProfit ? '+' : ''}{formatKRW(grand.total_profit)}
                </td>
                <td style={{ color: isGrandProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 800 }}>
                  {formatPercent(grand.total_profit_pct)}
                </td>
                <td>-</td>
                <td style={{ fontWeight: 800 }}>100.00%</td>
                <td>-</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. [USER REQUIREMENT] Aggregated Asset Breakdown Table */}
      <div className="section-card">
        <div className="section-title">
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TrendingUp size={18} color="var(--accent-primary)" />
            📈 종목별 통합 합산 현황 (여러 포트폴리오에 분산된 동일 종목 통합 집계)
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            여러 포트폴리오에 나누어 보유 중인 동일 종목을 가중평균 평단가와 통합 수량으로 합산한 지표입니다.
          </span>
        </div>

        <div className="table-container">
          <table className="custom-table">
            <thead>
              <tr>
                <th>종목명 (티커)</th>
                <th>시장</th>
                <th>통합 보유수량</th>
                <th>통합 평단가 (가중평균)</th>
                <th>실시간 현재가</th>
                <th>총 평가금액{currencyMode === 'USD' ? '' : '(원)'}</th>
                <th>평가 손익{currencyMode === 'USD' ? '' : '(원)'}</th>
                <th>수익률(%)</th>
                <th>전체 자산 비중(%)</th>
                <th>포트폴리오별 보유 분산</th>
              </tr>
            </thead>
            <tbody>
              {aggregatedAssets.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '30px', color: 'var(--text-secondary)' }}>
                    보유 중인 종목이 없습니다.
                  </td>
                </tr>
              ) : (
                aggregatedAssets.map((item) => {
                  const isUs = item.market === 'US';
                  const isUsdMode = currencyMode === 'USD' && isUs;
                  const isProfit = isUsdMode ? ((item.total_profit_usd || 0) >= 0) : ((item.total_profit || 0) >= 0);
                  const isCryptoItem = item.asset_type === 'CRYPTO';

                  return (
                    <tr key={item.key}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '1.1rem' }}>
                            {isCryptoItem ? (item.ticker === 'BTC' ? '🪙' : '💎') : '📈'}
                          </span>
                          <div>
                            <strong style={{ fontSize: '0.94rem', color: isCryptoItem ? '#F59E0B' : 'inherit' }}>
                              {item.name}
                            </strong>
                            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                              {item.ticker}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${item.market === 'US' ? 'badge-primary' : (isCryptoItem ? 'badge-warning' : 'badge-secondary')}`}>
                          {item.market}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600 }}>
                        {isCryptoItem 
                          ? `${Number(item.total_quantity).toFixed(8).replace(/\.?0+$/, '')} ${item.ticker}` 
                          : `${Number(item.total_quantity).toLocaleString()}주`}
                      </td>
                      <td>{isUsdMode ? formatUSD(item.weighted_avg_price_usd) : formatKRW(item.weighted_avg_price)}</td>
                      <td>{isUsdMode ? formatUSD(item.current_price_usd) : formatKRW(item.current_price)}</td>
                      <td style={{ fontWeight: 700, color: 'var(--accent-primary)' }}>
                        {isUsdMode ? formatUSD(item.total_eval_amount_usd) : formatKRW(item.total_eval_amount)}
                      </td>
                      <td style={{ color: isProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                        {isUsdMode ? formatUSD(item.total_profit_usd, true) : `${isProfit ? '+' : ''}${formatKRW(item.total_profit)}`}
                      </td>
                      <td style={{ color: isProfit ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                        {formatPercent(isUsdMode ? item.total_profit_pct_usd : item.total_profit_pct)}
                      </td>
                      <td style={{ fontWeight: 700 }}>
                        {item.weight_in_grand_total_pct?.toFixed(2)}%
                      </td>
                      <td>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                          {item.distribution?.map((d, dIdx) => (
                            <span 
                              key={dIdx} 
                              className="badge" 
                              style={{ 
                                background: 'var(--bg-surface)', 
                                border: '1px solid var(--border-color)',
                                fontSize: '0.74rem',
                                color: 'var(--text-secondary)'
                              }}
                              title={isUsdMode ? `평단가: ${formatUSD(d.avg_price_usd)}, 평가액: ${formatUSD(d.eval_amount_usd)}` : `평단가: ${formatKRW(d.avg_price)}, 평가액: ${formatKRW(d.eval_amount)}`}
                            >
                              <strong>{d.portfolio_name}</strong>: {isCryptoItem ? `${d.quantity} ${item.ticker}` : `${d.quantity}주`}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
