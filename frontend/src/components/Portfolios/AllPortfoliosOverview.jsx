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

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Sparkles, RefreshCw, CheckSquare, Square } from 'lucide-react';
import { api } from '../../utils/api';

import { createOverviewCache } from '../../utils/overviewCache';
import MarketStatus from '../common/MarketStatus';
import { useMarketRevalidation } from '../../utils/useMarketRevalidation';
import { assetClassBreakdown } from '../../utils/assetClasses';
import OverviewCharts from './OverviewCharts';
import PortfolioComparisonTable from './PortfolioComparisonTable';
import AggregatedAssetsTable from './AggregatedAssetsTable';
import OverviewSummaryCards from './OverviewSummaryCards';

const overviewCache = createOverviewCache();

export default function AllPortfoliosOverview({
  onSelectPortfolio,
  currencyMode = 'KRW',
  forceRefreshOnMount = false,
  onMarketUpdate,
}) {
  const [data, setData] = useState(() => overviewCache.get(true));
  const [loading, setLoading] = useState(() => !overviewCache.get(true));
  const [refreshing, setRefreshing] = useState(false);
  const [includeCrypto, setIncludeCrypto] = useState(true);
  const [error, setError] = useState('');
  const requestSequence = useRef(0);
  const initialRefresh = useRef(forceRefreshOnMount);

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

  // 전체 순자산 구성: 보유자산과 예수금의 합이 중앙 총자산과 일치해야 함.
  const assetClassDonutData = useMemo(() =>
    assetClassBreakdown(data?.aggregated_assets, 'total_eval_amount', {
      includeCrypto: true,
      cashKrw: Number(data?.grand_total?.total_cash_krw) || 0,
    }),
  [data?.aggregated_assets, data?.grand_total?.total_cash_krw]);

  const loadOverview = useCallback(async (isRefresh = false, cryptoToggle = includeCrypto) => {
    const sequence = ++requestSequence.current;
    if (isRefresh) setRefreshing(true);
    else if (!overviewCache.get(cryptoToggle)) setLoading(true);
    setError('');

    try {
      const res = await api.getPortfoliosOverview(cryptoToggle, isRefresh);
      if (sequence !== requestSequence.current) return;
      overviewCache.set(cryptoToggle, res);
      setData(res);
      onMarketUpdate?.(res);
    } catch (err) {
      if (sequence !== requestSequence.current) return;
      console.error('Failed to load portfolios overview:', err);
      setError(err.message || '전체 자산 종합 요약을 불러오는 중 오류가 발생했습니다.');
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [includeCrypto, onMarketUpdate]);

  useEffect(() => {
    const force = initialRefresh.current;
    initialRefresh.current = false;
    loadOverview(force, includeCrypto);
    return () => { requestSequence.current += 1; };
  }, [loadOverview, includeCrypto]);

  useMarketRevalidation(data?.market_status, () => loadOverview(false, includeCrypto), includeCrypto, !refreshing);

  const handleToggleCrypto = () => {
    const nextVal = !includeCrypto;
    requestSequence.current += 1;
    const cached = overviewCache.get(nextVal);
    setData(cached);
    setLoading(!cached);
    setRefreshing(false);
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
      <MarketStatus status={data?.market_status} />
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', margin: 0 }}>
        보유자산 수익률 = (평가손익 + 세후 배당) ÷ 보유자산 매입원가. 예수금은 총자산에만 포함됩니다.
      </p>
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

      <OverviewSummaryCards
        portfolios={portfolios}
        includeCrypto={includeCrypto}
        crypto={crypto}
        currencyMode={currencyMode}
        grand={grand}
        portfolioColors={portfolioColors}
      />

      <OverviewCharts
        setChartView={setChartView}
        chartView={chartView}
        portfolioDonutData={portfolioDonutData}
        grand={grand}
        assetClassDonutData={assetClassDonutData}
      />

      <PortfolioComparisonTable
        portfolios={portfolios}
        portfolioColors={portfolioColors}
        onSelectPortfolio={onSelectPortfolio}
        includeCrypto={includeCrypto}
        crypto={crypto}
        grand={grand}
        isGrandProfit={isGrandProfit}
      />

      <AggregatedAssetsTable currencyMode={currencyMode} aggregatedAssets={aggregatedAssets} />

    </div>
  );
}
