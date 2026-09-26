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
import { 
  ShieldAlert, 
  ChevronDown, ChevronUp, Edit2, RefreshCw, PieChart 
} from 'lucide-react';
import { formatKRW, formatUSD, formatQuantity, formatPercent, getProfitColor } from '../../utils/formatters';
import DriftBar from '../common/DriftBar';
import DonutChart from '../common/DonutChart';
import EditHoldingsModal from './EditHoldingsModal';
import { api } from '../../utils/api';

export default function DashboardTab({ 
  dashboardData, 
  assets, 
  accounts, 
  currencyMode = 'KRW',
  onRefresh 
}) {
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [expandedAccs, setExpandedAccs] = useState({});
  const [syncingNamuh, setSyncingNamuh] = useState(false);
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
      if (activeAssetIds.has(String(item.asset_id))) return true;
      return (item.quantity || 0) > 0;
    });
  }, [stock_assets, activeAssetIds]);

  // 예금 포함/제외 필터가 적용된 자산 목록
  const displayStockAssets = useMemo(() => {
    if (includeDeposits) return visibleStockAssets;
    return (visibleStockAssets || []).filter((item) => !item.is_deposit);
  }, [visibleStockAssets, includeDeposits]);

  // 예금 포함/제외에 따른 동적 KPI 재계산
  const displayKpi = useMemo(() => {
    if (includeDeposits) return kpi;
    const totalBuy = displayStockAssets.reduce((sum, item) => sum + (Number(item.buy_amount) || 0), 0);
    const totalEval = displayStockAssets.reduce((sum, item) => sum + (Number(item.eval_amount) || 0), 0);
    const totalProfit = totalEval - totalBuy;
    const totalReturn = totalBuy > 0 ? (totalProfit / totalBuy * 100) : 0;
    return {
      ...kpi,
      total_stock_buy: totalBuy,
      total_stock_eval: totalEval,
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
    const usStockProfit = usStockEval - usStockBuy;
    const usStockReturn = usStockBuy > 0 ? (usStockProfit / usStockBuy * 100) : 0;
    const usCash = Number(cash_assets?.usd_cash) || 0;

    // KRW assets (Non-US stocks, gold, deposits)
    const krStocks = (displayStockAssets || []).filter(item => item.market !== 'US');
    const krStockEval = krStocks.reduce((sum, item) => sum + (Number(item.eval_amount) || 0), 0);
    const krStockBuy = krStocks.reduce((sum, item) => sum + (Number(item.buy_amount) || 0), 0);
    const krStockProfit = krStockEval - krStockBuy;
    const krStockReturn = krStockBuy > 0 ? (krStockProfit / krStockBuy * 100) : 0;
    const krCash = Number(cash_assets?.krw_cash) || 0;

    return {
      usd: {
        total_eval: usStockEval,
        total_buy: usStockBuy,
        total_profit: usStockProfit,
        total_return: usStockReturn,
        cash: usCash,
        isProfit: usStockProfit >= 0
      },
      krw: {
        total_eval: krStockEval,
        total_buy: krStockBuy,
        total_profit: krStockProfit,
        total_return: krStockReturn,
        cash: krCash,
        isProfit: krStockProfit >= 0
      }
    };
  }, [displayStockAssets, cash_assets]);

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

  // 종목 유형별 자산 분류 헬퍼 함수
  const classifyAssetType = (item) => {
    if (!item) return '주식';
    if (item.is_deposit) return '예금';

    const name = (item.name || '').toLowerCase();
    const ticker = (item.ticker || '').toUpperCase();

    // 1. 예금
    if (
      item.is_deposit || 
      item.asset_type === 'DEPOSIT' || 
      ticker.startsWith('DEP') || 
      name.includes('예금') || 
      name.includes('적금') || 
      name.includes('새마을') || 
      name.includes('금고')
    ) {
      return '예금';
    }

    // 2. 대체투자 (원자재파생ETF, 금99.99 등)
    if (
      name.includes('금99') || 
      name.includes('금 99') || 
      name.includes('원자재') || 
      name.includes('gold') || 
      name.includes('commodity') ||
      ticker === 'PDBC' ||
      ticker === 'M04020000'
    ) {
      return '대체투자';
    }

    // 3. 채권 (미국10년국채액티브, 미국30년국채액티브 등)
    if (
      name.includes('국채') || 
      name.includes('채권') || 
      name.includes('bond') ||
      ticker === '0085P0' ||
      ticker === '476760'
    ) {
      return '채권';
    }

    // 4. 주식 (미국나스닥100, 미국배당다우존스, 뱅가드세계주식, 차이나CSI300, 차이나H 등)
    return '주식';
  };

  // 종목 유형별(주식/채권/대체투자/예금) 비중 도넛 차트 데이터 가공 (선택에 따라 예금 포함 또는 제외)
  const assetTypeDonutData = useMemo(() => {
    const categories = {
      '주식': { label: '📈 주식', value: 0, color: '#3B82F6' },
      '채권': { label: '📜 채권', value: 0, color: '#8B5CF6' },
      '대체투자': { label: '🥇 대체투자', value: 0, color: '#EAB308' },
      '예금': { label: '🏦 예금', value: 0, color: '#10B981' },
    };

    (displayStockAssets || []).forEach((item) => {
      const evalAmt = Number(item.eval_amount) || 0;
      if (evalAmt <= 0) return;

      const typeKey = classifyAssetType(item);
      if (categories[typeKey]) {
        categories[typeKey].value += evalAmt;
      } else {
        categories['주식'].value += evalAmt;
      }
    });

    return Object.values(categories)
      .filter((cat) => cat.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [displayStockAssets]);

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
  const isProfit = (displayKpi?.total_stock_profit || 0) >= 0;

  const toggleAccordion = (accId) => {
    setExpandedAccs((prev) => ({
      ...prev,
      [accId]: prev[accId] === false ? true : false
    }));
  };

  const handleSyncNamuh = async () => {
    setSyncingNamuh(true);
    try {
      const res = await api.syncNamuh();
      alert(res.message || 'NH투자증권 잔고 동기화 완료!');
      onRefresh();
    } catch (err) {
      alert(`동기화 실패: ${err.message}`);
    } finally {
      setSyncingNamuh(false);
    }
  };

  const handleToggleExhaust = async (accId, isExhausted) => {
    try {
      await api.toggleLimitExhausted(accId, isExhausted);
      onRefresh();
    } catch (err) {
      alert(`한도 소진 상태 변경 실패: ${err.message}`);
    }
  };

  return (
    <div>
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

      {/* 1. Top KPI Summary Cards (USD 모드: 방안 1 2단 압축 카드 / KRW 모드: 기본 4개 카드) */}
      {currencyMode === 'USD' ? (
        <div className="dual-currency-kpi-grid">
          {/* 1) 🇺🇸 외화 자산 종합 (USD) */}
          <div className="dual-kpi-card usd-card">
            <div className="dual-kpi-header">
              <div className="dual-kpi-title">
                <span className="badge badge-accent">🇺🇸 외화 자산 종합 (USD)</span>
                <span className="dual-kpi-subtitle">미국 상장 자산 & 외화 예수금</span>
              </div>
              <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.1)', color: 'var(--accent-primary)', fontSize: '0.74rem' }}>
                외화 순자산 {formatUSD(displayDualKpi.usd.total_eval + displayDualKpi.usd.cash)}
              </span>
            </div>
            <div className="dual-kpi-main">
              <div className="dual-kpi-main-label">외화 총 평가금액</div>
              <div className="dual-kpi-main-value" style={{ color: 'var(--accent-primary)' }}>
                {formatUSD(displayDualKpi.usd.total_eval)}
              </div>
              <div className="dual-kpi-sub-row">
                <span className="dual-kpi-sub-label">외화 평가손익:</span>
                <span className="dual-kpi-sub-value" style={{ color: getProfitColor(displayDualKpi.usd.total_profit) }}>
                  {formatUSD(displayDualKpi.usd.total_profit, true)} ({formatPercent(displayDualKpi.usd.total_return)})
                </span>
              </div>
            </div>
            <div className="dual-kpi-footer">
              <div className="dual-kpi-footer-item">
                <span>외화 투자원금</span>
                <strong>{formatUSD(displayDualKpi.usd.total_buy)}</strong>
              </div>
              <div className="dual-kpi-footer-divider" />
              <div className="dual-kpi-footer-item">
                <span>외화 예수금</span>
                <strong style={{ color: 'var(--accent-primary)' }}>{formatUSD(displayDualKpi.usd.cash)}</strong>
              </div>
            </div>
          </div>

          {/* 2) 🇰🇷 원화 자산 종합 (KRW) */}
          <div className="dual-kpi-card krw-card">
            <div className="dual-kpi-header">
              <div className="dual-kpi-title">
                <span className="badge badge-safe">🇰🇷 원화 자산 종합 (KRW)</span>
                <span className="dual-kpi-subtitle">국내 주식·채권·금현물·예금 & 원화 예수금</span>
              </div>
              <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-safe)', fontSize: '0.74rem' }}>
                원화 순자산 {formatKRW(displayDualKpi.krw.total_eval + displayDualKpi.krw.cash)}
              </span>
            </div>
            <div className="dual-kpi-main">
              <div className="dual-kpi-main-label">원화 총 평가금액 {includeDeposits ? '' : '(예금 제외)'}</div>
              <div className="dual-kpi-main-value" style={{ color: 'var(--color-safe)' }}>
                {formatKRW(displayDualKpi.krw.total_eval)}
              </div>
              <div className="dual-kpi-sub-row">
                <span className="dual-kpi-sub-label">원화 평가손익:</span>
                <span className="dual-kpi-sub-value" style={{ color: getProfitColor(displayDualKpi.krw.total_profit) }}>
                  {formatKRW(displayDualKpi.krw.total_profit, true)} ({formatPercent(displayDualKpi.krw.total_return)})
                </span>
              </div>
            </div>
            <div className="dual-kpi-footer">
              <div className="dual-kpi-footer-item">
                <span>원화 투자원금</span>
                <strong>{formatKRW(displayDualKpi.krw.total_buy)}</strong>
              </div>
              <div className="dual-kpi-footer-divider" />
              <div className="dual-kpi-footer-item">
                <span>원화 예수금</span>
                <strong style={{ color: 'var(--color-safe)' }}>{formatKRW(displayDualKpi.krw.cash)}</strong>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-title">🛒 총 투자 매입금액 {includeDeposits ? '(원금)' : '(예금 제외)'}</div>
            <div className="kpi-value">{formatKRW(displayKpi?.total_stock_buy)}</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-title">📈 총 투자 평가금액 {includeDeposits ? '' : '(예금 제외)'}</div>
            <div className="kpi-value">{formatKRW(displayKpi?.total_stock_eval)}</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-title">총 평가 손익 {includeDeposits ? '' : '(예금 제외)'}</div>
            <div className="kpi-value" style={{ color: getProfitColor(displayKpi?.total_stock_profit) }}>
              {(displayKpi?.total_stock_profit || 0) > 0 ? '+' : ''}{formatKRW(displayKpi?.total_stock_profit)}
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-title">총 수익률 {includeDeposits ? '' : '(예금 제외)'}</div>
            <div className="kpi-value" style={{ color: getProfitColor(displayKpi?.total_stock_return) }}>
              {formatPercent(displayKpi?.total_stock_return)}
            </div>
          </div>
        </div>
      )}

      {/* 2. Interactive Donut Charts Section (개별 종목별 / 종목 유형별 비중) */}
      <div className="section-card" style={{ marginBottom: '20px' }}>
        <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PieChart size={18} color="var(--accent-primary)" />
            포트폴리오 비중 분석 (도넛 차트)
          </span>

          <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-surface)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('both')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'both' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'both' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              종목 & 유형 듀얼
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('stocks')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'stocks' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'stocks' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              개별 종목별
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setChartView('types')}
              style={{
                padding: '4px 10px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: chartView === 'types' ? 'var(--accent-primary)' : 'transparent',
                color: chartView === 'types' ? '#FFF' : 'var(--text-secondary)',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              종목 유형별
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
          {(chartView === 'both' || chartView === 'stocks') && (
            <div style={{ 
              background: 'var(--bg-surface)', 
              padding: '16px 20px', 
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)' 
            }}>
              <DonutChart
                title={includeDeposits ? "📈 개별 종목별 자산 평가액 비중" : "📈 개별 종목별 자산 평가액 비중 (예금 제외)"}
                data={stockDonutData}
                centerLabel={includeDeposits ? "투자자산 총 평가액" : "투자자산 총 평가액 (예금 제외)"}
                centerValue={formatKRW(totalStockEval)}
                size={230}
              />
            </div>
          )}

          {(chartView === 'both' || chartView === 'types') && (
            <div style={{ 
              background: 'var(--bg-surface)', 
              padding: '16px 20px', 
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)' 
            }}>
              <DonutChart
                title={includeDeposits ? "🏛️ 종목 유형별 자산 평가액 비중 (주식/채권/대체투자/예금)" : "🏛️ 종목 유형별 자산 평가액 비중 (주식/채권/대체투자)"}
                data={assetTypeDonutData}
                centerLabel={includeDeposits ? "투자자산 총 평가액" : "투자자산 총 평가액 (예금 제외)"}
                centerValue={formatKRW(totalStockEval)}
                size={230}
              />
            </div>
          )}
        </div>
      </div>

      {/* 3. Stock Assets Section */}
      <div className="section-card">
        <div className="section-title">
          <span>📈 투자 자산 현황 {includeDeposits ? '(주식/ETF/금/예금)' : '(주식/ETF/금 · 예금 제외)'}</span>
          <button 
            className="btn btn-secondary btn-sm"
            onClick={() => setIsEditModalOpen(true)}
          >
            <Edit2 size={14} /> 보유 잔고/예수금 직접 수정
          </button>
        </div>

        {/* 💻 DESKTOP TABLES (Screen > 768px) */}
        <div className="desktop-view">
          {/* Table 1: Basic Information */}
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
            [자산 기본 정보]
          </h4>
          <div className="table-container" style={{ marginBottom: '24px' }}>
            <table className="custom-table">
              <thead>
                <tr>
                  <th>종목명</th>
                  <th>보유 수량</th>
                  <th>수익률(%)</th>
                  <th>손익{currencyMode === 'USD' ? '' : '(원)'}</th>
                  <th>평가금액{currencyMode === 'USD' ? '' : '(원)'}</th>
                  <th>평단가{currencyMode === 'USD' ? '' : '(원)'}</th>
                  <th>현재가{currencyMode === 'USD' ? '' : '(원)'}</th>
                </tr>
              </thead>
              <tbody>
                {displayStockAssets?.map((item) => {
                  const isUs = item.market === 'US';
                  const isUsdMode = currencyMode === 'USD' && isUs;
                  const itemProfit = isUsdMode ? (item.profit_usd || 0) : (item.profit_krw || 0);
                  const itemReturn = isUsdMode ? (item.profit_pct_usd !== undefined ? item.profit_pct_usd : item.profit_pct) : item.profit_pct;

                  return (
                    <tr key={item.asset_id}>
                      <td style={{ fontWeight: 600 }}>
                        {item.name}
                        {isUs && (
                          <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                            🇺🇸 US
                          </span>
                        )}
                        {item.is_deposit && (
                          <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                            🏦 예금
                          </span>
                        )}
                        {item.is_deposit && item.account_no && (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                            계좌: {item.account_no}
                          </div>
                        )}
                      </td>
                      <td>{formatQuantity(item.quantity, item.unit)}</td>
                      <td style={{ color: getProfitColor(itemReturn), fontWeight: 700 }}>
                        {formatPercent(itemReturn)}
                      </td>
                      <td style={{ color: getProfitColor(itemProfit), fontWeight: 700 }}>
                        {isUsdMode ? formatUSD(item.profit_usd, true) : `${itemProfit > 0 ? '+' : ''}${formatKRW(item.profit_krw)}`}
                      </td>
                      <td style={{ fontWeight: 600 }}>
                        {isUsdMode ? formatUSD(item.eval_amount_usd) : formatKRW(item.eval_amount)}
                      </td>
                      <td>
                        {isUsdMode ? formatUSD(item.avg_price_usd) : formatKRW(item.avg_price)}
                      </td>
                      <td>
                        {isUsdMode ? formatUSD(item.current_price_usd) : formatKRW(item.current_price)}
                      </td>
                    </tr>
                  );
                })}
                {/* Total Row */}
                <tr className="total-row">
                  <td>{includeDeposits ? '총합계' : '총합계 (예금 제외)'}</td>
                  <td>-</td>
                  <td style={{ fontWeight: 700 }}>
                    {currencyMode === 'USD' ? (
                      <span>
                        <span style={{ color: getProfitColor(displayDualKpi.usd.total_return) }}>
                          🇺🇸 {formatPercent(displayDualKpi.usd.total_return)}
                        </span>
                        <span style={{ margin: '0 6px', color: 'var(--text-muted)' }}>|</span>
                        <span style={{ color: getProfitColor(displayDualKpi.krw.total_return) }}>
                          🇰🇷 {formatPercent(displayDualKpi.krw.total_return)}
                        </span>
                      </span>
                    ) : (
                      <span style={{ color: getProfitColor(displayKpi?.total_stock_return) }}>
                        {formatPercent(displayKpi?.total_stock_return)}
                      </span>
                    )}
                  </td>
                  <td style={{ fontWeight: 700 }}>
                    {currencyMode === 'USD' ? (
                      <span>
                        <span style={{ color: getProfitColor(displayDualKpi.usd.total_profit) }}>
                          🇺🇸 {formatUSD(displayDualKpi.usd.total_profit, true)}
                        </span>
                        <span style={{ margin: '0 6px', color: 'var(--text-muted)' }}>|</span>
                        <span style={{ color: getProfitColor(displayDualKpi.krw.total_profit) }}>
                          🇰🇷 {formatKRW(displayDualKpi.krw.total_profit, true)}
                        </span>
                      </span>
                    ) : (
                      <span style={{ color: getProfitColor(displayKpi?.total_stock_profit) }}>
                        {(displayKpi?.total_stock_profit || 0) > 0 ? '+' : ''}{formatKRW(displayKpi?.total_stock_profit)}
                      </span>
                    )}
                  </td>
                  <td style={{ fontWeight: 700 }}>
                    {currencyMode === 'USD' ? (
                      <span>
                        🇺🇸 {formatUSD(displayDualKpi.usd.total_eval)}
                        <span style={{ margin: '0 4px', color: 'var(--text-muted)' }}>|</span>
                        🇰🇷 {formatKRW(displayDualKpi.krw.total_eval)}
                      </span>
                    ) : (
                      formatKRW(displayKpi?.total_stock_eval)
                    )}
                  </td>
                  <td>-</td>
                  <td>-</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Table 2: Weights & Bidirectional Drift Chart */}
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
            [비중 및 괴리율]
          </h4>
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>종목명</th>
                  <th style={{ textAlign: 'center' }}>현 비중(%)</th>
                  <th style={{ textAlign: 'center' }}>목표비중(%)</th>
                  <th style={{ textAlign: 'center', width: '220px' }}>괴리율(%)</th>
                </tr>
              </thead>
              <tbody>
                {weightDriftAssets?.map((item) => (
                  <tr key={item.asset_id}>
                    <td style={{ fontWeight: 600 }}>{item.name}</td>
                    <td style={{ textAlign: 'center', fontWeight: 600 }}>
                      {item.weight_pct.toFixed(1)}%
                    </td>
                    <td style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
                      {item.target_weight_pct.toFixed(1)}%
                    </td>
                    <td>
                      <DriftBar drift={item.drift_pct} scaleMax={drift_scale_max} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 📱 MOBILE RESPONSIVE CARDS (Screen <= 768px) */}
        <div className="mobile-view">
          {displayStockAssets?.map((item) => {
            const isUs = item.market === 'US';
            const isUsdMode = currencyMode === 'USD' && isUs;
            const itemProfit = isUsdMode ? (item.profit_usd || 0) : (item.profit_krw || 0);
            const incRebal = item.include_in_rebalance !== false;

            return (
              <div key={item.asset_id} className="mobile-card-item">
                {/* Row 1: Name + Eval Amount */}
                <div className="mobile-card-row">
                  <div className="mobile-card-title">
                    <span>{item.name}</span>
                    {isUs && (
                      <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                        🇺🇸 US
                      </span>
                    )}
                    {item.is_deposit ? (
                      <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                        🏦 예금 {item.account_no ? `(${item.account_no})` : ''}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '6px', whiteSpace: 'nowrap' }}>({item.ticker})</span>
                    )}
                    {!incRebal && (
                      <span className="badge" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(156, 163, 175, 0.2)', color: 'var(--text-muted)' }}>
                        비중 제외
                      </span>
                    )}
                  </div>
                  <span className="mobile-card-value">
                    {isUsdMode ? formatUSD(item.eval_amount_usd) : formatKRW(item.eval_amount)}
                  </span>
                </div>

                {/* Row 2: Quantity & Prices + Profit/Loss */}
                <div className="mobile-card-row">
                  <span className="mobile-card-subtext">
                    <span>{formatQuantity(item.quantity, item.unit)}</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span>평단 {isUsdMode ? formatUSD(item.avg_price_usd) : formatKRW(item.avg_price)}</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span>현재 {isUsdMode ? formatUSD(item.current_price_usd) : formatKRW(item.current_price)}</span>
                  </span>
                  <span className="mobile-card-stat" style={{ color: getProfitColor(itemProfit) }}>
                    {isUsdMode ? (
                      `${formatUSD(item.profit_usd, true)} (${formatPercent(item.profit_pct_usd !== undefined ? item.profit_pct_usd : item.profit_pct)})`
                    ) : (
                      `${itemProfit > 0 ? '+' : ''}${formatKRW(item.profit_krw)} (${formatPercent(item.profit_pct)})`
                    )}
                  </span>
                </div>

                {/* Row 3: Weight info & Drift (투자 자산만 표시, 예금형 자산은 완전 제외) */}
                {!item.is_deposit && incRebal && (
                  <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-color)' }}>
                    <div className="mobile-card-row" style={{ fontSize: '0.82rem', marginBottom: '6px' }}>
                      <span style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        현재 <strong>{item.weight_pct.toFixed(1)}%</strong> / 목표 <strong>{item.target_weight_pct.toFixed(1)}%</strong>
                      </span>
                      <span style={{ fontWeight: 700, whiteSpace: 'nowrap', color: item.drift_pct > 0 ? 'var(--color-profit)' : item.drift_pct < 0 ? 'var(--color-loss)' : 'var(--text-muted)' }}>
                        괴리율: {item.drift_pct > 0 ? '+' : ''}{item.drift_pct.toFixed(1)}%
                      </span>
                    </div>
                    <DriftBar drift={item.drift_pct} scaleMax={drift_scale_max} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Cash Assets Section */}
      <div className="section-card">
        <div className="section-title">
          <span>💵 현금성 자산 (예수금)</span>
        </div>

        {/* Desktop Table */}
        <div className="desktop-view">
          <div className="table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>구분</th>
                  <th>보유 외화 수량</th>
                  <th>원화 환산 평가금액(원)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600 }}>💵 원화 현금 (KRW)</td>
                  <td>-</td>
                  <td>{formatKRW(cash_assets?.krw_cash)}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>💵 달러 현금 (USD)</td>
                  <td>{formatUSD(cash_assets?.usd_cash)}</td>
                  <td>{formatKRW(cash_assets?.usd_cash_krw)}</td>
                </tr>
                <tr className="total-row">
                  <td>총합계</td>
                  <td>-</td>
                  <td>{formatKRW(cash_assets?.total_cash_krw)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Mobile Cards */}
        <div className="mobile-view">
          <div className="mobile-card-item">
            <div className="mobile-card-row">
              <span style={{ fontWeight: 600 }}>💵 원화 현금 (KRW)</span>
              <span style={{ fontWeight: 700 }}>{formatKRW(cash_assets?.krw_cash)}</span>
            </div>
            <div className="mobile-card-row" style={{ marginTop: '8px' }}>
              <span style={{ fontWeight: 600 }}>💵 달러 현금 (USD)</span>
              <span style={{ fontWeight: 700 }}>
                {formatUSD(cash_assets?.usd_cash)} <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>({formatKRW(cash_assets?.usd_cash_krw)})</span>
              </span>
            </div>
            <div className="mobile-card-row" style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-color)' }}>
              <span style={{ fontWeight: 700 }}>총 현금 합계</span>
              <span style={{ fontWeight: 800, fontSize: '1.05rem', color: 'var(--accent-primary)' }}>{formatKRW(cash_assets?.total_cash_krw)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Accounts Breakdown Section */}
      <div className="section-card">
        <div className="section-title">
          <span>💳 계좌별 자산 현황 & 한도 모니터링</span>
          <button 
            className="btn btn-secondary btn-sm"
            onClick={handleSyncNamuh}
            disabled={syncingNamuh}
            title="NH투자증권 나무 계좌 잔고 일괄 동기화"
          >
            <RefreshCw size={14} className={syncingNamuh ? 'animate-spin' : ''} />
            {syncingNamuh ? '동기화 중...' : '나무 API 잔고 동기화'}
          </button>
        </div>

        {!includeDeposits && (
          <div style={{
            marginBottom: '14px',
            padding: '8px 12px',
            background: 'rgba(99, 102, 241, 0.08)',
            border: '1px solid rgba(99, 102, 241, 0.2)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.82rem',
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <span>💡 <strong>예금 제외 모드:</strong> 정기예금 전용 계좌 및 각 계좌 내 예금 보유분이 제외된 순수 투자자산 기준입니다.</span>
          </div>
        )}

        {displayAccSummaries.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', padding: '12px 0' }}>
            {includeDeposits ? '등록된 계좌가 없습니다.' : '등록된 투자 계좌가 없습니다. (예금 제외 모드)'}
          </p>
        ) : (
          displayAccSummaries.map((acc) => {
            const isExpanded = expandedAccs[acc.id] !== false; // default true
            const isIrp = acc.account_type === 'IRP';
            const isIrpOverRisk = isIrp && acc.risk_pct > 70.0;
            const accStockProfit = acc.profit_krw || ((acc.stock_eval || 0) - (acc.stock_buy_total || 0));
            const accStockReturn = acc.profit_pct || (acc.stock_buy_total > 0 ? (accStockProfit / acc.stock_buy_total * 100) : 0);
            const isAccProfit = accStockProfit >= 0;
            const totalVal = acc.total_val || (acc.stock_eval + acc.deposit_krw + (acc.deposit_usd * (usd_krw || 1380)));

            const annualPct = (acc.annual_limit_pct || 0) * 100;
            const taxPct = (acc.tax_limit_pct || 0) * 100;

            return (
              <div key={acc.id} className="account-accordion">
                {/* Accordion Header */}
                <div className="accordion-header" onClick={() => toggleAccordion(acc.id)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: '1.05rem' }}>
                      📌 [{acc.account_type === '정기예금' ? '🏦 정기예금' : acc.account_type}] {acc.account_alias}
                    </span>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      ({acc.account_no})
                    </span>
                    {acc.account_type !== '정기예금' && (
                      <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.15)', color: 'var(--accent-primary)' }}>
                        우선순위: {acc.priority || 99}
                      </span>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block' }}>계좌 총 자산</span>
                      <span style={{ fontWeight: 800, fontSize: '1.05rem', color: 'var(--text-primary)' }}>{formatKRW(totalVal)}</span>
                    </div>
                    {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                  </div>
                </div>

                {/* Accordion Body */}
                {isExpanded && (
                  <div className="accordion-body">
                    {/* Account Stat Highlight Row */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', background: 'var(--bg-surface)', padding: '14px 16px', borderRadius: 'var(--radius-md)', marginBottom: '16px', border: '1px solid var(--border-color)' }}>
                      <div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          {acc.account_type === '정기예금' ? '🏦 예금 평가금액' : '📈 주식 평가금액'}
                        </div>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700 }}>{formatKRW(acc.stock_eval)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>손익 (수익률)</div>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700, color: getProfitColor(accStockProfit) }}>
                          {(accStockProfit || 0) > 0 ? '+' : ''}{formatKRW(accStockProfit)} ({formatPercent(accStockReturn)})
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>💵 보유 예수금</div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>
                          원화 {formatKRW(acc.deposit_krw)} {acc.deposit_usd > 0 && `| 달러 ${formatUSD(acc.deposit_usd)}`}
                        </div>
                      </div>
                    </div>

                    {/* IRP Risk Banner */}
                    {isIrp && (
                      <div className={`alert-banner ${isIrpOverRisk ? 'alert-danger' : 'alert-success'}`} style={{ marginBottom: '16px' }}>
                        <ShieldAlert size={18} />
                        <span>
                          <strong>IRP 위험자산 비중: {acc.risk_pct?.toFixed(1) || 0}%</strong> / 70.0% 제한 —{' '}
                          {isIrpOverRisk ? '⚠️ 70% 초과! 안전자산 비중을 늘려주세요.' : '✅ 규정 준수 중'}
                        </span>
                      </div>
                    )}

                    {/* Limits Progress Bars */}
                    {acc.annual_limit > 0 && (
                      <div className="progress-bar-container">
                        <div className="progress-bar-label">
                          <span>연간 납입한도 ({formatKRW(acc.annual_limit)} 중 약 {annualPct.toFixed(1)}% 소진)</span>
                          <strong>{annualPct.toFixed(1)}%</strong>
                        </div>
                        <div className="progress-track">
                          <div 
                            className="progress-fill" 
                            style={{ 
                            width: `${Math.min(100, annualPct)}%`,
                            background: annualPct > 100 ? 'var(--color-risk)' : 'var(--accent-primary)'
                          }} 
                        />
                      </div>
                    </div>
                  )}

                  {acc.tax_limit > 0 && (
                    <div className="progress-bar-container">
                      <div className="progress-bar-label">
                        <span>세액공제 한도 ({formatKRW(acc.tax_limit)} 중 약 {taxPct.toFixed(1)}% 소진)</span>
                        <strong>{taxPct.toFixed(1)}%</strong>
                      </div>
                      <div className="progress-track">
                        <div 
                          className="progress-fill" 
                          style={{ 
                            width: `${Math.min(100, taxPct)}%`,
                            background: taxPct > 100 ? 'var(--color-risk)' : '#10B981'
                          }} 
                        />
                      </div>
                    </div>
                  )}

                  {/* Limit Exhaustion Toggle (96% 이상 또는 소진 완료 시) */}
                  {acc.can_exhaust_limit && (
                    <div style={{
                      marginTop: '12px',
                      marginBottom: '4px',
                      padding: '10px 14px',
                      background: acc.is_limit_exhausted ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                      border: `1px solid ${acc.is_limit_exhausted ? 'rgba(16, 185, 129, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
                      borderRadius: 'var(--radius-md)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '8px'
                    }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.86rem', fontWeight: 600, color: acc.is_limit_exhausted ? '#10B981' : 'var(--text-primary)' }}>
                        <input
                          type="checkbox"
                          checked={!!acc.is_limit_exhausted}
                          onChange={(e) => handleToggleExhaust(acc.id, e.target.checked)}
                          style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                        />
                        <span>
                          {acc.is_limit_exhausted 
                            ? '🔒 연간 납입한도 소진 완료 (리밸런싱 추가 입금 차단 중)' 
                            : '💡 한도 96% 이상 도달: [한도 소진 완료]로 처리하시겠습니까?'}
                        </span>
                      </label>
                      {acc.is_limit_exhausted && (
                        <span className="badge" style={{ background: '#10B981', color: '#fff', fontSize: '0.75rem', padding: '2px 8px' }}>
                          100% 소진 완료
                        </span>
                      )}
                    </div>
                  )}

                  {/* Account Holdings List */}
                  <div style={{ marginTop: '16px' }}>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '10px' }}>
                      📦 계좌별 보유 종목 ({acc.holdings?.length || 0}개)
                    </div>

                    {/* Desktop Holdings Table */}
                    <div className="desktop-view">
                      <div className="table-container">
                        <table className="custom-table" style={{ fontSize: '0.86rem' }}>
                          <thead>
                            <tr>
                              <th>종목명</th>
                              <th>티커</th>
                              <th>보유수량</th>
                              <th>평단가</th>
                              <th>현재가</th>
                              <th>평가금액</th>
                              <th>손익(수익률)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {acc.holdings?.map((h) => {
                              const isHUs = h.market === 'US';
                              const isHUsdMode = currencyMode === 'USD' && isHUs;
                              const isHProfit = isHUsdMode ? ((h.profit_usd || 0) >= 0) : ((h.profit_krw || 0) >= 0);

                              return (
                                <tr key={h.asset_id}>
                                  <td style={{ fontWeight: 700 }}>
                                    {h.asset_name}
                                    {isHUs && (
                                      <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                        🇺🇸 US
                                      </span>
                                    )}
                                    {h.is_deposit && (
                                      <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                        🏦 예금
                                      </span>
                                    )}
                                  </td>
                                  <td>{h.ticker}</td>
                                  <td>{formatQuantity(h.quantity, h.unit)}</td>
                                  <td>{isHUsdMode ? formatUSD(h.avg_price_usd) : formatKRW(h.avg_price)}</td>
                                  <td>{isHUsdMode ? formatUSD(h.current_price_usd) : formatKRW(h.current_price)}</td>
                                  <td style={{ fontWeight: 700 }}>{isHUsdMode ? formatUSD(h.eval_amount_usd) : formatKRW(h.eval_amount)}</td>
                                  <td style={{ color: getProfitColor(isHUsdMode ? h.profit_usd : h.profit_krw), fontWeight: 700 }}>
                                    {isHUsdMode ? formatUSD(h.profit_usd, true) : `${(h.profit_krw || 0) > 0 ? '+' : ''}${formatKRW(h.profit_krw)}`} ({formatPercent(isHUsdMode ? h.profit_pct_usd : h.profit_pct)})
                                  </td>
                                </tr>
                              );
                            })}
                            <tr>
                              <td style={{ fontWeight: 700 }} colSpan={5}>💵 원화 예수금</td>
                              <td style={{ fontWeight: 800 }}>{formatKRW(acc.deposit_krw)}</td>
                              <td>-</td>
                            </tr>
                            {(Number(acc.deposit_usd) > 0 || currencyMode === 'USD') && (
                              <tr>
                                <td style={{ fontWeight: 700 }} colSpan={5}>💵 외화 예수금 (USD)</td>
                                <td style={{ fontWeight: 800, color: 'var(--accent-primary)' }}>{formatUSD(acc.deposit_usd)}</td>
                                <td>-</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Mobile Holdings Cards */}
                    <div className="mobile-view">
                      {acc.holdings?.map((h) => {
                        const isHUs = h.market === 'US';
                        const isHUsdMode = currencyMode === 'USD' && isHUs;
                        const isHProfit = isHUsdMode ? ((h.profit_usd || 0) >= 0) : ((h.profit_krw || 0) >= 0);

                        return (
                          <div key={h.asset_id} className="mobile-card-item" style={{ background: 'var(--bg-surface)' }}>
                            <div className="mobile-card-row">
                              <div className="mobile-card-title">
                                <span>{h.asset_name}</span>
                                {isHUs && (
                                  <span className="badge badge-accent" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                    🇺🇸 US
                                  </span>
                                )}
                                {h.is_deposit ? (
                                  <span className="badge badge-safe" style={{ marginLeft: '6px', fontSize: '0.72rem', padding: '2px 6px' }}>
                                    🏦 예금
                                  </span>
                                ) : (
                                  <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginLeft: '6px', whiteSpace: 'nowrap' }}>({h.ticker})</span>
                                )}
                              </div>
                              <span className="mobile-card-value">
                                {isHUsdMode ? formatUSD(h.eval_amount_usd) : formatKRW(h.eval_amount)}
                              </span>
                            </div>
                            <div className="mobile-card-row">
                              <span className="mobile-card-subtext">
                                <span>{formatQuantity(h.quantity, h.unit)}</span>
                                <span style={{ color: 'var(--text-muted)' }}>·</span>
                                <span>평단 {isHUsdMode ? formatUSD(h.avg_price_usd) : formatKRW(h.avg_price)}</span>
                                <span style={{ color: 'var(--text-muted)' }}>·</span>
                                <span>현재 {isHUsdMode ? formatUSD(h.current_price_usd) : formatKRW(h.current_price)}</span>
                              </span>
                              <span className="mobile-card-stat" style={{ color: getProfitColor(isHUsdMode ? h.profit_usd : h.profit_krw) }}>
                                {isHUsdMode ? (
                                  `${formatUSD(h.profit_usd, true)} (${formatPercent(h.profit_pct_usd !== undefined ? h.profit_pct_usd : h.profit_pct)})`
                                ) : (
                                  `${(h.profit_krw || 0) > 0 ? '+' : ''}${formatKRW(h.profit_krw)} (${formatPercent(h.profit_pct)})`
                                )}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                      <div className="mobile-card-item" style={{ background: 'var(--bg-surface)' }}>
                        <div className="mobile-card-row">
                          <span style={{ fontWeight: 700 }}>💵 원화 예수금</span>
                          <span className="mobile-card-value" style={{ color: 'var(--text-primary)' }}>{formatKRW(acc.deposit_krw)}</span>
                        </div>
                        {(Number(acc.deposit_usd) > 0 || currencyMode === 'USD') && (
                          <div className="mobile-card-row" style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid var(--border-color)' }}>
                            <span style={{ fontWeight: 700 }}>💵 외화 예수금 (USD)</span>
                            <span className="mobile-card-value" style={{ color: 'var(--accent-primary)' }}>{formatUSD(acc.deposit_usd)}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })
      )}
      </div>

      {/* Edit Holdings Modal */}
      {isEditModalOpen && (
        <EditHoldingsModal
          accounts={accounts}
          assets={assets}
          usdKrw={dashboardData?.usd_krw || 1350}
          onClose={() => setIsEditModalOpen(false)}
          onSaved={() => {
            setIsEditModalOpen(false);
            onRefresh();
          }}
        />
      )}
    </div>
  );
}
