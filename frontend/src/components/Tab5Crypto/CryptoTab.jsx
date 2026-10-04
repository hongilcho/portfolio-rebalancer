/**
 * 탭 5-1. 가상자산(암호화폐) 대시보드 컴포넌트 (CryptoTab.jsx)
 * ==============================================================
 * 업비트 실시간 시세를 기반으로 소유자(홍일, 윤아)별 비트코인(BTC), 이더리움(ETH)의
 * 보유 수량, 평가금액, 수익률 및 소유자간 지분율/코인별 배분 도넛 차트를 제공합니다.
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Coins, RefreshCw, Edit3 } from 'lucide-react';
import { api } from '../../utils/api';

import EditCryptoModal from './EditCryptoModal';
import MarketStatus from '../common/MarketStatus';
import { useMarketRevalidation } from '../../utils/useMarketRevalidation';
import CryptoSummaryCards from './CryptoSummaryCards';
import CryptoCharts from './CryptoCharts';
import CryptoOwnerCards from './CryptoOwnerCards';
import CryptoCombinedCards from './CryptoCombinedCards';
import CryptoComparisonTable from './CryptoComparisonTable';

export default function CryptoTab({ 
  currentPortfolioId = 'default', forceRefreshOnMount = false
}) {
  const [data, setData] = useState(null);
  const requestSequence = useRef(0);
  const dataRef = useRef(data);
  dataRef.current = data;
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
    const list = data?.crypto_assets_combined || [];
    return list
      .map(c => ({
        label: `${c.name || c.symbol} (${c.symbol})`,
        value: Number(c.eval_amount) || 0,
        color: symbolColors[c.symbol] || '#06B6D4'
      }))
      .filter(c => c.value > 0);
  }, [data?.crypto_assets_combined]);

  const loadCryptoSummary = useCallback(async (isRefresh = false) => {
    const sequence = ++requestSequence.current;
    if (isRefresh && dataRef.current) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      const res = await api.getCryptoSummary(currentPortfolioId, isRefresh);
      if (sequence !== requestSequence.current) return;
      setData(res);
    } catch (err) {
      if (sequence !== requestSequence.current) return;
      console.error('Failed to load crypto summary:', err);
      setError(err.message || '가상화폐 데이터를 불러오는 중 오류가 발생했습니다.');
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [currentPortfolioId]);

  useEffect(() => {
    loadCryptoSummary(forceRefreshOnMount);
    return () => { requestSequence.current += 1; };
  }, [loadCryptoSummary, forceRefreshOnMount]);

  useMarketRevalidation(data?.market_status, () => loadCryptoSummary(false), currentPortfolioId, !refreshing);

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

  const isCryptoProfit = (cryptoTotal.total_profit || 0) >= 0;
  const isHongilProfit = (hongil.total_profit || 0) >= 0;
  const isYoonaProfit = (yoona.total_profit || 0) >= 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <MarketStatus status={data?.market_status} />
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

      <CryptoSummaryCards
        cryptoTotal={cryptoTotal}
        isCryptoProfit={isCryptoProfit}
        hongil={hongil}
        yoona={yoona}
      />

      <CryptoCharts
        setChartView={setChartView}
        chartView={chartView}
        ownerDonutData={ownerDonutData}
        cryptoTotal={cryptoTotal}
        coinDonutData={coinDonutData}
      />

      <CryptoOwnerCards
        hongil={hongil}
        isHongilProfit={isHongilProfit}
        hongilBtc={hongilBtc}
        hongilEth={hongilEth}
        yoona={yoona}
        isYoonaProfit={isYoonaProfit}
        yoonaBtc={yoonaBtc}
        yoonaEth={yoonaEth}
      />

      <CryptoCombinedCards
        hongilBtc={hongilBtc}
        yoonaBtc={yoonaBtc}
        btcComb={btcComb}
        hongilEth={hongilEth}
        yoonaEth={yoonaEth}
        ethComb={ethComb}
      />

      <CryptoComparisonTable
        hongilBtc={hongilBtc}
        hongilEth={hongilEth}
        hongil={hongil}
        isHongilProfit={isHongilProfit}
        yoonaBtc={yoonaBtc}
        yoonaEth={yoonaEth}
        yoona={yoona}
        isYoonaProfit={isYoonaProfit}
        cryptoTotal={cryptoTotal}
        isCryptoProfit={isCryptoProfit}
      />

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
