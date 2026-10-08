/**
 * 탭 1. 포트폴리오 현황 컴포넌트 (DashboardTab.jsx)
 * ===================================================
 * 현재 선택된 포트폴리오의 총 순자산(NAV), 평가손익, 자산군별 비중,
 * 계좌별 예수금/보유현황, 목표 비중 대비 괴리율(DriftBar)을 시각화합니다.
 * 
 * 주요 기능:
 * - 상단 KPI 카드: 총 평가금액, 총 투자원금, 평가손익 및 수익률
 * - 예금 포함/비포함 토글: 정기예금을 제외한 순수 투자자산 기준 비중/차트 전환
 * - 자산 배분 도넛 차트: 종목별 및 계좌별 자산 비중 비교
 * - 목표 비중 대비 괴리율 시각화(DriftBar)
 * - 계좌별 상세 잔고 아코디언 및 보유 수량 편집 모달 연동
 * 
 * @param {object} props.dashboardData - 백엔드에서 수신한 대시보드 종합 데이터
 * @param {Array} props.assets - 등록된 자산 마스터 목록
 * @param {Array} props.accounts - 등록된 계좌 마스터 목록
 * @param {Function} props.onRefresh - 데이터 새로고침 트리거 콜백
 */

import React, { useState, useMemo } from 'react';

import MarketStatus from '../common/MarketStatus';
import { sortInvestmentAssets, assetClassBreakdown } from '../../utils/assetClasses';
import DashboardSummaryCards from './DashboardSummaryCards';
import DashboardCharts from './DashboardCharts';
import InvestmentAssetsSection from './InvestmentAssetsSection';
import CashAssetsSection from './CashAssetsSection';
import AccountBreakdown from './AccountBreakdown';


export default function DashboardTab({ 
  dashboardData, 
  assets, 
  currencyMode = 'KRW',
}) {
  const [expandedAccs, setExpandedAccs] = useState({});
  const [chartView, setChartView] = useState('both'); // 'both' | 'stocks' | 'accounts'
  const [includeDeposits, setIncludeDeposits] = useState(() => {
    try {
      const saved = sessionStorage.getItem('dashboard_include_deposits');
      return saved !== null ? JSON.parse(saved) : true;
    } catch {
      return true;
    }
  });

  const handleToggleIncludeDeposits = (val) => {
    setIncludeDeposits(val);
    try {
      sessionStorage.setItem('dashboard_include_deposits', JSON.stringify(val));
    } catch {}
  };

  const safeData = dashboardData || {};
  const {
    kpi = {},
    stock_assets = [],
    cash_assets = {},
    drift_scale_max,
    usd_krw = 1380
  } = safeData;

  const activeAssetIds = useMemo(() => {
    return new Set(
      (assets || []).filter((a) => a.is_active !== false).map((a) => String(a.id))
    );
  }, [assets]);

  const visibleStockAssets = useMemo(() => {
    return (stock_assets || []).filter((item) => {
      // 1번 탭: 비활성화 종목 또는 보유 수량이 0 이하인 자산(예금 제외)은 표에서 제외
      if (!activeAssetIds.has(String(item.asset_id))) return false;
      if (item.is_deposit) return true;
      return (Number(item.quantity) || 0) > 0;
    });
  }, [stock_assets, activeAssetIds]);

  // 예금 포함/제외 필터가 적용된 자산 목록
  const displayStockAssets = useMemo(() => {
    if (includeDeposits) return visibleStockAssets;
    return (visibleStockAssets || []).filter((item) => !item.is_deposit);
  }, [visibleStockAssets, includeDeposits]);

  // 예금 포함/제외에 따른 동적 KPI 재계산
  const displayKpi = useMemo(() => {
    if (!kpi) return null;
    if (includeDeposits) return kpi;
    const totalBuy = displayStockAssets.reduce((sum, item) => sum + (Number(item.buy_amount) || 0), 0);
    const totalEval = displayStockAssets.reduce((sum, item) => sum + (Number(item.eval_amount) || 0), 0);
    const totalEvalProfit = totalEval - totalBuy;
    const totalDividendProfit = displayStockAssets.reduce((sum, item) => sum + (Number(item.dividend_profit_krw) || 0), 0);
    const totalProfit = totalEvalProfit + totalDividendProfit;
    const totalReturn = totalBuy > 0 ? (totalProfit / totalBuy * 100) : 0;
    const totalEvalReturn = totalBuy > 0 ? (totalEvalProfit / totalBuy * 100) : 0;
    return {
      ...kpi,
      total_stock_buy: totalBuy,
      total_stock_eval: totalEval,
      total_eval_profit: totalEvalProfit,
      total_eval_return: totalEvalReturn,
      total_dividend_profit: totalDividendProfit,
      total_stock_profit: totalProfit,
      total_stock_return: totalReturn
    };
  }, [kpi, displayStockAssets, includeDeposits]);

  // 외화(USD) 및 원화(KRW) 듀얼 통화 종합 집계 (방안 1)
  const displayDualKpi = useMemo(() => {
    // USD assets (US market stocks)
    const usStocks = (displayStockAssets || []).filter(item => item.market === 'US');
    const usStockEval = usStocks.reduce((sum, item) => sum + (Number(item.eval_amount_usd) || 0), 0);
    const usStockBuy = usStocks.reduce((sum, item) => sum + (Number(item.buy_amount_usd) || 0), 0);
    const usStockEvalProfit = usStockEval - usStockBuy;
    const usStockDividend = usStocks.reduce((sum, item) => sum + (Number(item.dividend_profit_usd) || 0), 0);
    const usStockProfit = usStockEvalProfit + usStockDividend;
    const usStockReturn = usStockBuy > 0 ? (usStockProfit / usStockBuy * 100) : 0;
    const usStockEvalReturn = usStockBuy > 0 ? (usStockEvalProfit / usStockBuy * 100) : 0;
    const usCash = Number(cash_assets?.usd_cash) || 0;

    const totalFxProfitKrw = usStocks.reduce((sum, item) => sum + (Number(item.fx_profit_krw) || 0), 0);
    const totalPureStockProfitKrw = usStocks.reduce((sum, item) => sum + (Number(item.pure_stock_profit_krw) || 0), 0);
    const totalBuyKrw = usStocks.reduce((sum, item) => sum + (Number(item.buy_amount) || 0), 0);
    const weightedBuyFxRate = usStockBuy > 0 ? (totalBuyKrw / usStockBuy) : (kpi?.usd_summary?.weighted_buy_fx_rate || 0);
    const totalFxProfitPct = (weightedBuyFxRate > 0 && totalBuyKrw > 0) ? (totalFxProfitKrw / totalBuyKrw * 100) : 0;

    // KRW assets (Non-US stocks, gold, deposits)
    const krStocks = (displayStockAssets || []).filter(item => item.market !== 'US');
    const krStockEval = krStocks.reduce((sum, item) => sum + (Number(item.eval_amount) || 0), 0);
    const krStockBuy = krStocks.reduce((sum, item) => sum + (Number(item.buy_amount) || 0), 0);
    const krStockEvalProfit = krStockEval - krStockBuy;
    const krStockDividend = krStocks.reduce((sum, item) => sum + (Number(item.dividend_profit_krw) || 0), 0);
    const krStockProfit = krStockEvalProfit + krStockDividend;
    const krStockReturn = krStockBuy > 0 ? (krStockProfit / krStockBuy * 100) : 0;
    const krStockEvalReturn = krStockBuy > 0 ? (krStockEvalProfit / krStockBuy * 100) : 0;
    const krCash = Number(cash_assets?.krw_cash) || 0;

    return {
      usd: {
        total_eval: usStockEval,
        total_buy: usStockBuy,
        total_profit: usStockProfit,
        total_return: usStockReturn,
        eval_profit: usStockEvalProfit,
        eval_return: usStockEvalReturn,
        dividend_profit: usStockDividend,
        cash: usCash,
        isProfit: usStockProfit >= 0,
        total_fx_profit_krw: totalFxProfitKrw,
        total_fx_profit_pct: totalFxProfitPct,
        pure_stock_profit_krw: totalPureStockProfitKrw,
        weighted_buy_fx_rate: weightedBuyFxRate
      },
      krw: {
        total_eval: krStockEval,
        total_buy: krStockBuy,
        total_profit: krStockProfit,
        total_return: krStockReturn,
        eval_profit: krStockEvalProfit,
        eval_return: krStockEvalReturn,
        dividend_profit: krStockDividend,
        cash: krCash,
        isProfit: krStockProfit >= 0
      }
    };
  }, [displayStockAssets, cash_assets, kpi?.usd_summary]);

  const accSummaries = useMemo(() => {
    return dashboardData?.account_summaries || dashboardData?.accounts || [];
  }, [dashboardData?.account_summaries, dashboardData?.accounts]);

  // '비중 및 괴리율' 표 전용 데이터 (예금형 자산 및 비중 제외 자산은 아예 삭제/제외)
  const weightDriftAssets = useMemo(() => {
    return (displayStockAssets || []).filter((item) => {
      if (item.is_deposit) return false;
      if (item.include_in_rebalance === false) return false;
      return true;
    });
  }, [displayStockAssets]);

  // 종목별 비중 도넛 차트 데이터 가공 (선택에 따라 예금 포함 또는 제외)
  const stockDonutData = useMemo(() => {
    return (displayStockAssets || [])
      .filter((item) => (Number(item.eval_amount) || 0) > 0)
      .map((item) => ({
        label: item.name,
        value: Number(item.eval_amount),
        subLabel: item.is_deposit ? '예금' : '투자자산'
      }))
      .sort((a, b) => b.value - a.value);
  }, [displayStockAssets]);

  // 표·모바일 카드와 두 화면의 자산군 차트는 같은 분류 규칙을 사용합니다.
  const investmentAssets = useMemo(() => sortInvestmentAssets(displayStockAssets), [displayStockAssets]);

  const assetTypeDonutData = useMemo(() =>
    assetClassBreakdown(displayStockAssets, 'eval_amount'),
  [displayStockAssets]);

  // 계좌별 자산 현황 (예금 제외 모드 시 정기예금 계좌 및 각 계좌의 예금 자산 제외)
  const displayAccSummaries = useMemo(() => {
    if (includeDeposits) return accSummaries;
    return (accSummaries || [])
      .filter((acc) => acc.account_type !== '정기예금')
      .map((acc) => {
        const nonDepositHoldings = (acc.holdings || []).filter((h) => !h.is_deposit);
        const stockEval = nonDepositHoldings.reduce((sum, h) => sum + (Number(h.eval_amount) || 0), 0);
        const stockBuy = nonDepositHoldings.reduce((sum, h) => sum + (Number(h.avg_price) * Number(h.quantity) || 0), 0);
        const profitKrw = stockEval - stockBuy;
        const profitPct = stockBuy > 0 ? (profitKrw / stockBuy * 100) : 0;
        const totalVal = stockEval + (Number(acc.deposit_krw) || 0) + ((Number(acc.deposit_usd) || 0) * (usd_krw || 1380));
        return {
          ...acc,
          holdings: nonDepositHoldings,
          stock_eval: stockEval,
          stock_buy_total: stockBuy,
          profit_krw: profitKrw,
          profit_pct: profitPct,
          total_val: totalVal
        };
      });
  }, [accSummaries, includeDeposits, usd_krw]);

  if (!dashboardData) {
    return <div className="section-card">데이터를 불러오는 중입니다...</div>;
  }

  const totalStockEval = Number(displayKpi?.total_stock_eval) || 0;

  const toggleAccordion = (accId) => {
    setExpandedAccs((prev) => ({
      ...prev,
      [accId]: prev[accId] === false ? true : false
    }));
  };

  return (
    <div>
      <MarketStatus status={dashboardData?.market_status} />
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
        보유자산 수익률 = (평가손익 + 세후 배당) ÷ 보유자산 매입원가. 예수금은 총자산에만 포함됩니다.
      </p>
      {/* 0. Top Filter & View Toggle Bar (예금 포함/제외 토글 스위치) */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '12px',
        marginBottom: '20px',
        padding: '12px 18px',
        background: 'var(--bg-card)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-color)',
        boxShadow: 'var(--shadow-sm)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.96rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {includeDeposits ? '📊 포트폴리오 종합 현황' : '🎯 순수 투자자산 현황'}
          </span>
          <span className="badge" style={{
            fontSize: '0.75rem',
            padding: '3px 8px',
            background: includeDeposits ? 'rgba(16, 185, 129, 0.12)' : 'rgba(99, 102, 241, 0.15)',
            color: includeDeposits ? '#10B981' : 'var(--accent-primary)',
            border: `1px solid ${includeDeposits ? 'rgba(16, 185, 129, 0.25)' : 'rgba(99, 102, 241, 0.25)'}`
          }}>
            {includeDeposits ? '🏦 예금 합산 표시 중' : '📈 예금 제외 (주식·채권·대체투자 전용)'}
          </span>
        </div>

        {/* Interactive Toggle Switch */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => handleToggleIncludeDeposits(!includeDeposits)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleToggleIncludeDeposits(!includeDeposits);
            }
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '10px',
            cursor: 'pointer',
            userSelect: 'none',
            background: 'var(--bg-surface)',
            padding: '6px 14px',
            borderRadius: 'var(--radius-full)',
            border: '1px solid var(--border-color)',
            transition: 'all 0.2s ease'
          }}
          title={includeDeposits ? '클릭하여 예금 제외 (주식/채권/대체투자만 보기)' : '클릭하여 예금 포함하여 보기'}
        >
          <span style={{
            fontSize: '0.84rem',
            fontWeight: 600,
            color: 'var(--text-primary)'
          }}>
            {includeDeposits ? '🏦 예금 포함' : '🚫 예금 제외'}
          </span>

          <div style={{
            position: 'relative',
            width: '42px',
            height: '22px',
            borderRadius: '11px',
            background: includeDeposits ? 'var(--accent-primary)' : 'var(--text-muted)',
            padding: '2px',
            transition: 'background 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
            flexShrink: 0
          }}>
            <div style={{
              width: '18px',
              height: '18px',
              borderRadius: '50%',
              background: '#FFFFFF',
              boxShadow: '0 1px 3px rgba(0,0,0,0.35)',
              transform: includeDeposits ? 'translateX(20px)' : 'translateX(0px)',
              transition: 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
            }} />
          </div>
        </div>
      </div>

      <DashboardSummaryCards
        currencyMode={currencyMode}
        displayDualKpi={displayDualKpi}
        includeDeposits={includeDeposits}
        displayKpi={displayKpi}
      />

      <DashboardCharts
        setChartView={setChartView}
        chartView={chartView}
        includeDeposits={includeDeposits}
        stockDonutData={stockDonutData}
        totalStockEval={totalStockEval}
        assetTypeDonutData={assetTypeDonutData}
      />

      <InvestmentAssetsSection
        includeDeposits={includeDeposits}
        currencyMode={currencyMode}
        displayStockAssets={displayStockAssets}
        investmentAssets={investmentAssets}
        displayDualKpi={displayDualKpi}
        displayKpi={displayKpi}
        weightDriftAssets={weightDriftAssets}
        drift_scale_max={drift_scale_max}
      />

      <CashAssetsSection cash_assets={cash_assets} />


      <AccountBreakdown
        includeDeposits={includeDeposits}
        displayAccSummaries={displayAccSummaries}
        expandedAccs={expandedAccs}
        usd_krw={usd_krw}
        toggleAccordion={toggleAccordion}
        currencyMode={currencyMode}
      />


    </div>
  );
}
