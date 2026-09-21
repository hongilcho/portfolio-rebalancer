import React, { useState, useEffect } from 'react';
import { 
  BarChart3, Target, Scale, History, Settings, ShieldCheck, 
  RefreshCw, Coins 
} from 'lucide-react';
import { api } from './utils/api';
import Header from './components/Header';
import AuthModal from './components/AuthModal';
import DashboardTab from './components/Tab1Dashboard/DashboardTab';
import WeightsTab from './components/Tab2Weights/WeightsTab';
import RebalanceTab from './components/Tab3Rebalance/RebalanceTab';
import HistoryTab from './components/Tab4History/HistoryTab';
import CryptoTab from './components/Tab5Crypto/CryptoTab';
import SettingsTab from './components/Tab5Settings/SettingsTab';
import ManagePortfoliosModal from './components/Portfolios/ManagePortfoliosModal';
import AllPortfoliosOverview from './components/Portfolios/AllPortfoliosOverview';

const TABS = [
  { id: 'tab1', label: '📊 1. 포트폴리오 현황', icon: BarChart3 },
  { id: 'tab2', label: '🎯 2. 목표 비중 설정', icon: Target },
  { id: 'tab3', label: '⚖️ 3. 리밸런싱 전략', icon: Scale },
  { id: 'tab4', label: '📝 4. 매매 기록', icon: History },
  { id: 'tab5', label: '🪙 5. 가상화폐 자산', icon: Coins },
  { id: 'tab6', label: '⚙️ 6. 기초 환경 세팅', icon: Settings },
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

  // Portfolios State
  const [portfolios, setPortfolios] = useState([]);
  const [currentPortfolioId, setCurrentPortfolioId] = useState(() => {
    return localStorage.getItem('active_portfolio_id') || 'default';
  });
  const [isManagePortfoliosOpen, setIsManagePortfoliosOpen] = useState(false);

  // Global Data
  const [dashboardData, setDashboardData] = useState(null);
  const [assets, setAssets] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [pricesData, setPricesData] = useState(null);
  const [usdKrw, setUsdKrw] = useState(1380.0);
  const [rateSource, setRateSource] = useState('');

  // Apply Theme to document root
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('portfolio_theme', theme);
  }, [theme]);

  const handleSelectPortfolio = (pid) => {
    setCurrentPortfolioId(pid);
    localStorage.setItem('active_portfolio_id', pid);
  };

  const loadAllData = async (forceRefresh = false, targetPid = currentPortfolioId) => {
    if (forceRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      // Always fetch portfolios list and prices
      const [portsRes, pricesRes] = await Promise.all([
        api.getPortfolios(),
        api.getPrices(forceRefresh),
      ]);
      setPortfolios(portsRes.portfolios || []);
      setPricesData(pricesRes);

      // If viewing a specific portfolio (not 'all')
      if (targetPid !== 'all') {
        const [dashRes, assetsRes, accountsRes] = await Promise.all([
          api.getDashboardSummary(targetPid),
          api.getAssets(targetPid),
          api.getAccounts(targetPid),
        ]);

        setDashboardData(dashRes);
        setAssets(assetsRes.assets || []);
        setAccounts(accountsRes.accounts || []);
        setUsdKrw(dashRes.usd_krw || pricesRes.usd_krw || 1380.0);
        setRateSource(dashRes.rate_source || pricesRes.rate_source || '');
      } else {
        setUsdKrw(pricesRes.usd_krw || 1380.0);
        setRateSource(pricesRes.rate_source || '');
      }
    } catch (err) {
      console.error('Failed to load portfolio data:', err);
      setError(err.message || '데이터를 불러오는 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      loadAllData(false, currentPortfolioId);
    }
  }, [isAuthenticated, currentPortfolioId]);

  if (!isAuthenticated) {
    return <AuthModal onAuthenticated={() => setIsAuthenticated(true)} />;
  }

  const priceMap = pricesData?.price_map || {};

  return (
    <div className="app-container">
      {/* Header with Theme & Portfolio Selector */}
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
          <AllPortfoliosOverview 
            onSelectPortfolio={(id) => {
              if (id === 'tab_crypto') {
                handleSelectPortfolio('default');
                setActiveTab('tab5');
              } else {
                handleSelectPortfolio(id);
                setActiveTab('tab1');
              }
            }} 
          />
        </main>
      ) : (
        <>
          {/* Tabs Navigation for individual portfolio */}
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
              {activeTab === 'tab1' && (
                <DashboardTab
                  dashboardData={dashboardData}
                  assets={assets}
                  accounts={accounts}
                  onRefresh={() => loadAllData(false, currentPortfolioId)}
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
                  onRefresh={() => loadAllData(false, currentPortfolioId)}
                />
              )}

              {activeTab === 'tab4' && (
                <HistoryTab
                  assets={assets}
                  accounts={accounts}
                  priceMap={priceMap}
                  currentPortfolioId={currentPortfolioId}
                  onSaved={() => loadAllData(false, currentPortfolioId)}
                />
              )}

              {activeTab === 'tab5' && (
                <CryptoTab />
              )}

              {activeTab === 'tab6' && (
                <SettingsTab
                  pricesData={pricesData}
                  accounts={accounts}
                  assets={assets}
                  currentPortfolioId={currentPortfolioId}
                  onSaved={() => loadAllData(false, currentPortfolioId)}
                />
              )}
            </main>
          )}
        </>
      )}

      {/* Manage Portfolios Modal */}
      <ManagePortfoliosModal
        isOpen={isManagePortfoliosOpen}
        onClose={() => setIsManagePortfoliosOpen(false)}
        portfolios={portfolios}
        currentPortfolioId={currentPortfolioId}
        onSelectPortfolio={handleSelectPortfolio}
        onRefresh={() => loadAllData(false, currentPortfolioId)}
      />
    </div>
  );
}
