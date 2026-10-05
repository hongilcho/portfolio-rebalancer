/**
 * 포트폴리오 리밸런서 메인 루트 컴포넌트 (App.jsx)
 * =================================================
 * 전역 상태 관리, 테마 전환, 포트폴리오 선택, 세션 스토리지 캐시 복원,
 * 단일 번들 데이터 로딩 및 탭 네비게이션을 총괄하는 최상위 컴포넌트입니다.
 * 
 * 주요 기능:
 * 1. 단일 번들 로딩(loadAllData):
 *    - 포트폴리오 전환 또는 새로고침 시 1회의 API 호출로 전체 현황 일괄 수신
 * 2. 0초 반응성 세션 캐시:
 *    - 브라우저 sessionStorage를 활용하여 포트폴리오 전환 즉시 이전 대시보드를 렌더링
 * 3. 5대 핵심 탭 네비게이션:
 *    - 1. 포트폴리오 현황 (DashboardTab)
 *    - 2. 목표 비중 설정 (WeightsTab)
 *    - 3. 리밸런싱 전략 (RebalanceTab)
 *    - 4. 매매 기록 (HistoryTab)
 *    - 5. 계좌 마스터 관리 (SettingsTab)
 */

import React, { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react';
import { 
  BarChart3, Target, Scale, History, Settings, RefreshCw 
} from 'lucide-react';
import { api } from './utils/api';
import Header from './components/Header';
import AuthModal from './components/AuthModal';
import DashboardTab from './components/Tab1Dashboard/DashboardTab';
import ViewLoading from './components/common/ViewLoading';
import DeferredDialog from './components/common/DeferredDialog';
import { useMarketRevalidation } from './utils/useMarketRevalidation';

// Keep the initial dashboard eager; fetch other screens only when selected.
const WeightsTab = lazy(() => import('./components/Tab2Weights/WeightsTab'));
const RebalanceTab = lazy(() => import('./components/Tab3Rebalance/RebalanceTab'));
const HistoryTab = lazy(() => import('./components/Tab4History/HistoryTab'));
const CryptoTab = lazy(() => import('./components/Tab5Crypto/CryptoTab'));
const SettingsTab = lazy(() => import('./components/Tab5Settings/SettingsTab'));
const ManagePortfoliosModal = lazy(() => import('./components/Portfolios/ManagePortfoliosModal'));
const AllPortfoliosOverview = lazy(() => import('./components/Portfolios/AllPortfoliosOverview'));

const TABS = [
  { id: 'tab1', label: '📊 1. 포트폴리오 현황', icon: BarChart3 },
  { id: 'tab2', label: '🎯 2. 목표 비중 설정', icon: Target },
  { id: 'tab3', label: '⚖️ 3. 리밸런싱 전략', icon: Scale },
  { id: 'tab4', label: '📝 4. 매매 기록', icon: History },
  { id: 'tab5', label: '⚙️ 5. 계좌 마스터 관리', icon: Settings },
];

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return localStorage.getItem('portfolio_auth') === 'true';
  });

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('portfolio_theme') || 'dark';
  });

  const [activeTab, setActiveTab] = useState('tab1');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  // Currency Display Mode State ('KRW' | 'USD') - MTS Style
  const [currencyMode, setCurrencyMode] = useState(() => {
    return localStorage.getItem('portfolio_currency_mode') || 'KRW';
  });

  const handleCurrencyModeChange = (mode) => {
    setCurrencyMode(mode);
    localStorage.setItem('portfolio_currency_mode', mode);
  };

  // Portfolios State
  const [portfolios, setPortfolios] = useState([]);
  const [currentPortfolioId, setCurrentPortfolioId] = useState(() => {
    return localStorage.getItem('active_portfolio_id') || 'default';
  });
  const [isManagePortfoliosOpen, setIsManagePortfoliosOpen] = useState(false);

  // Global Data
  const [dashboardData, setDashboardData] = useState(() => {
    try {
      const pid = localStorage.getItem('active_portfolio_id') || 'default';
      const saved = sessionStorage.getItem('portfolio_dashboard_v2_' + pid);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [assets, setAssets] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [pricesData, setPricesData] = useState(null);
  const [usdKrw, setUsdKrw] = useState(1380.0);
  const [rateSource, setRateSource] = useState('');
  const updateMarketHeader = useCallback((snapshot) => {
    if (snapshot?.usd_krw) setUsdKrw(snapshot.usd_krw);
    if (snapshot?.rate_source) setRateSource(snapshot.rate_source);
  }, []);

  // Apply Theme to document root
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('portfolio_theme', theme);
  }, [theme]);

  const handleSelectPortfolio = (pid) => {
    setChildRefreshKey(0);
    setCurrentPortfolioId(pid);
    localStorage.setItem('active_portfolio_id', pid);
    // 복원 가능한 세션 캐시가 있는 경우 즉시 반영
    try {
      const saved = sessionStorage.getItem('portfolio_dashboard_v2_' + pid);
      if (saved) setDashboardData(JSON.parse(saved));
    } catch {}
  };

  const currentPortfolioIdRef = useRef(currentPortfolioId);
  currentPortfolioIdRef.current = currentPortfolioId;

  const dashboardDataRef = useRef(dashboardData);
  dashboardDataRef.current = dashboardData;

  const [childRefreshKey, setChildRefreshKey] = useState(0);
  const requestSequence = useRef(0);

  const loadAllData = useCallback(async (forceRefresh = false, targetPid = null) => {
    const pid = targetPid || currentPortfolioIdRef.current;
    const sequence = ++requestSequence.current;
    if (forceRefresh) {
      setRefreshing(true);
      setChildRefreshKey(k => k + 1);
    } else if (!dashboardDataRef.current) {
      setLoading(true);
    }
    setError('');

    try {
      // If viewing 'all' (전체 자산 종합 요약) or 'crypto', respective tabs handle their own data.
      // We only fetch portfolios list and lightweight exchange rate to keep header updated without blocking.
      if (pid === 'all' || pid === 'crypto') {
        const [portsRes, rateRes] = await Promise.all([
          api.getPortfolios(),
          api.getExchangeRate(),
        ]);
        if (sequence !== requestSequence.current || pid !== currentPortfolioIdRef.current) return;
        setPortfolios(portsRes.portfolios || []);
        if (rateRes) {
          setUsdKrw(rateRes.usd_krw || 1380.0);
          setRateSource(rateRes.rate_source || '');
        }
        return;
      }

      // If viewing a specific portfolio, fetch all portfolio-specific data in ONE single unified bundle request
      const bundle = await api.getPortfolioBundle(pid, forceRefresh);
      if (sequence !== requestSequence.current || pid !== currentPortfolioIdRef.current) return;

      setPortfolios(bundle.portfolios || []);
      setPricesData(bundle.prices_data);
      setDashboardData(bundle.dashboard);
      try {
        sessionStorage.setItem('portfolio_dashboard_v2_' + pid, JSON.stringify(bundle.dashboard));
      } catch {}
      setAssets(bundle.assets || []);
      setAccounts(bundle.accounts || []);
      setUsdKrw(bundle.usd_krw || 1380.0);
      setRateSource(bundle.rate_source || '');
    } catch (err) {
      if (sequence !== requestSequence.current || pid !== currentPortfolioIdRef.current) return;
      console.error('Failed to load portfolio data:', err);
      setError(err.message || '데이터를 불러오는 중 오류가 발생했습니다.');
    } finally {
      if (sequence === requestSequence.current && pid === currentPortfolioIdRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      loadAllData(false, currentPortfolioId);
    }
  }, [isAuthenticated, currentPortfolioId, loadAllData]);

  useMarketRevalidation(dashboardData?.market_status, () => loadAllData(false, currentPortfolioId),
    currentPortfolioId, isAuthenticated && !refreshing && !['all', 'crypto'].includes(currentPortfolioId));

  if (!isAuthenticated) {
    return <AuthModal onAuthenticated={() => setIsAuthenticated(true)} />;
  }

  const priceMap = pricesData?.price_map || {};

  return (
    <div className="app-container">
      {/* Header with Theme & Portfolio Selector & Currency Toggle */}
      <Header
        usdKrw={usdKrw}
        rateSource={rateSource}
        onRefresh={() => loadAllData(true, currentPortfolioId)}
        refreshing={refreshing}
        currentTheme={theme}
        onThemeChange={setTheme}
        portfolios={portfolios}
        currentPortfolioId={currentPortfolioId}
        onSelectPortfolio={handleSelectPortfolio}
        onOpenManagePortfolios={() => setIsManagePortfoliosOpen(true)}
        currencyMode={currencyMode}
        onCurrencyModeChange={handleCurrencyModeChange}
      />

      {/* Error Alert */}
      {error && (
        <div className="alert-banner alert-danger" style={{ marginBottom: '20px' }}>
          <span>⚠️ {error}</span>
        </div>
      )}

      {/* Content View: When 'all' is selected -> AllPortfoliosOverview */}
      {currentPortfolioId === 'all' ? (
        <main>
          <Suspense fallback={<ViewLoading />}>
            <AllPortfoliosOverview
              key={childRefreshKey}
              onMarketUpdate={updateMarketHeader}
              forceRefreshOnMount={childRefreshKey > 0}
              currencyMode={currencyMode}
              onSelectPortfolio={(id) => {
                if (id === 'tab_crypto' || id === 'crypto') {
                  handleSelectPortfolio('crypto');
                } else {
                  handleSelectPortfolio(id);
                  setActiveTab('tab1');
                }
              }}
            />
          </Suspense>
        </main>
      ) : currentPortfolioId === 'crypto' ? (
        /* Content View: When 'crypto' is selected -> Independent Crypto Dashboard */
        <main>
          <Suspense fallback={<ViewLoading />}>
            <CryptoTab key={childRefreshKey} forceRefreshOnMount={childRefreshKey > 0} currentPortfolioId={currentPortfolioId} />
          </Suspense>
        </main>
      ) : (
        <>
          {/* Tabs Navigation for individual financial portfolio */}
          <nav className="tabs-nav">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  className={`tab-btn ${isActive ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <Icon size={18} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Tab Contents */}
          {loading && !dashboardData ? (
            <div className="section-card" style={{ textAlign: 'center', padding: '60px 20px' }}>
              <RefreshCw size={32} className="animate-spin" style={{ margin: '0 auto 16px auto', color: 'var(--accent-primary)' }} />
              <p style={{ color: 'var(--text-secondary)' }}>포트폴리오 및 실시간 시세 데이터를 불러오는 중입니다...</p>
            </div>
          ) : (
            <main>
              <Suspense fallback={<ViewLoading />}>
                {activeTab === 'tab1' && (
                  <DashboardTab
                    dashboardData={dashboardData}
                    assets={assets}
                    accounts={accounts}
                    currencyMode={currencyMode}
                    onRefresh={() => loadAllData(true, currentPortfolioId)}
                  />
                )}

                {activeTab === 'tab2' && (
                  <WeightsTab
                    assets={assets}
                    accounts={accounts}
                    onSaved={() => loadAllData(false, currentPortfolioId)}
                  />
                )}

                {activeTab === 'tab3' && (
                  <RebalanceTab
                    onRefresh={() => loadAllData(true, currentPortfolioId)}
                    currentPortfolioId={currentPortfolioId}
                  />
                )}

                {activeTab === 'tab4' && (
                  <HistoryTab
                    key={currentPortfolioId}
                    assets={assets}
                    accounts={accounts}
                    priceMap={priceMap}
                    usdKrw={usdKrw}
                    pricesData={pricesData}
                    currentPortfolioId={currentPortfolioId}
                    onSaved={() => loadAllData(false, currentPortfolioId)}
                  />
                )}

                {activeTab === 'tab5' && (
                  <SettingsTab
                    pricesData={pricesData}
                    accounts={accounts}
                    assets={assets}
                    currentPortfolioId={currentPortfolioId}
                    onSaved={() => loadAllData(false, currentPortfolioId)}
                  />
                )}
              </Suspense>
            </main>
          )}
        </>
      )}

      {/* Manage Portfolios Modal */}
      <DeferredDialog isOpen={isManagePortfoliosOpen} onClose={() => setIsManagePortfoliosOpen(false)}>
        <ManagePortfoliosModal
          isOpen={isManagePortfoliosOpen}
          onClose={() => setIsManagePortfoliosOpen(false)}
          portfolios={portfolios}
          currentPortfolioId={currentPortfolioId}
          onSelectPortfolio={handleSelectPortfolio}
          onRefresh={() => loadAllData(false, currentPortfolioId)}
        />
      </DeferredDialog>
    </div>
  );
}
