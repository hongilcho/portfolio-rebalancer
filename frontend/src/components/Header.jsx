/**
 * 공통 네비게이션 헤더 컴포넌트 (Header.jsx)
 * ============================================
 * 상단 바에서 실시간 환율 조회/수정, 새로고침, 테마(Dark/Light/Sepia) 전환,
 * 포트폴리오 드롭다운 선택, 포트폴리오 관리 모달 및 CSV 백업 다운로드를 제공합니다.
 * 
 * @param {number} props.usdKrw - 현재 적용 중인 USD/KRW 환율
 * @param {string} props.rateSource - 환율 수집 출처
 * @param {Function} props.onRefresh - 데이터 새로고침 트리거
 * @param {boolean} props.refreshing - 새로고침 진행 중 여부
 * @param {string} props.currentTheme - 현재 테마 문자열
 * @param {Function} props.onThemeChange - 테마 변경 콜백
 * @param {Array} props.portfolios - 포트폴리오 목록
 * @param {string} props.currentPortfolioId - 현재 선택된 포트폴리오 ID
 * @param {Function} props.onSelectPortfolio - 포트폴리오 선택 콜백
 * @param {Function} props.onOpenManagePortfolios - 포트폴리오 관리 모달 열기 콜백
 */

import React, { useState } from 'react';
import { RefreshCw, Download, Edit3, DollarSign, TrendingUp, Moon, Sun, Coffee, Briefcase, Settings, Coins } from 'lucide-react';
import { api } from '../utils/api';
import { formatKRW } from '../utils/formatters';

export default function Header({ 
  usdKrw, 
  rateSource, 
  onRefresh, 
  refreshing,
  currentTheme,
  onThemeChange,
  portfolios = [],
  currentPortfolioId = 'default',
  onSelectPortfolio,
  onOpenManagePortfolios,
  currencyMode = 'KRW',
  onCurrencyModeChange
}) {
  const [isEditRateOpen, setIsEditRateOpen] = useState(false);
  const [customRate, setCustomRate] = useState(usdKrw || 1380);
  const [savingRate, setSavingRate] = useState(false);

  const handleSaveRate = async () => {
    setSavingRate(true);
    try {
      await api.overrideExchangeRate(Number(customRate));
      setIsEditRateOpen(false);
      onRefresh();
    } catch (err) {
      alert(`환율 설정 실패: ${err.message}`);
    } finally {
      setSavingRate(false);
    }
  };

  const handleResetRate = async () => {
    setSavingRate(true);
    try {
      await api.refreshExchangeRate();
      setIsEditRateOpen(false);
      onRefresh();
    } catch (err) {
      alert(`환율 초기화 실패: ${err.message}`);
    } finally {
      setSavingRate(false);
    }
  };

  const handleDownloadBackup = () => {
    window.location.href = api.getExportCsvUrl();
  };

  return (
    <header className="app-header">
      <div className="header-top">
        <div className="header-title-group">
          <h1>
            <TrendingUp size={28} color="var(--accent-primary)" />
            자산 배분 포트폴리오 매니저
          </h1>
          <p>
            계좌별 예수금, 보유 수량/평단가 관리 & IRP 위험자산 70% 제약 및 납입/세액공제 한도 모니터링
          </p>
        </div>

        {/* Portfolio Switcher & Manager */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '6px', 
            background: 'var(--bg-surface)', 
            padding: '5px 10px', 
            borderRadius: 'var(--radius-md)', 
            border: `1px solid ${currentPortfolioId === 'crypto' ? '#F59E0B' : 'var(--accent-primary)'}` 
          }}>
            {currentPortfolioId === 'crypto' ? (
              <Coins size={16} color="#F59E0B" />
            ) : (
              <Briefcase size={16} color="var(--accent-primary)" />
            )}
            <select
              value={currentPortfolioId}
              onChange={(e) => onSelectPortfolio(e.target.value)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-primary)',
                fontWeight: 700,
                fontSize: '0.92rem',
                cursor: 'pointer',
                outline: 'none',
                minWidth: '170px'
              }}
            >
              <option value="all" style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', fontWeight: 700 }}>
                🌐 [전체 자산 종합 요약]
              </option>
              <optgroup label="💼 금융 포트폴리오" style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)' }}>
                {portfolios.map(p => (
                  <option key={p.id} value={p.id} style={{ background: 'var(--bg-card)', color: 'var(--text-primary)' }}>
                    💼 {p.name} {p.is_default ? '(기본)' : ''}
                  </option>
                ))}
              </optgroup>
              <optgroup label="🪙 가상화폐" style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)' }}>
                <option value="crypto" style={{ background: 'var(--bg-card)', color: '#F59E0B', fontWeight: 700 }}>
                  🪙 가상화폐 포트폴리오 (업비트)
                </option>
              </optgroup>
            </select>
          </div>

          <button 
            className="btn btn-secondary btn-sm"
            onClick={onOpenManagePortfolios}
            title="포트폴리오 관리 (이름/설명 수정 및 신규 추가)"
            style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
          >
            <Settings size={13} />
            <span>포트폴리오 관리</span>
          </button>
        </div>

        <div className="header-controls">
          {/* Currency Display Mode Toggle (KRW / USD) - MTS Style */}
          <div className="theme-selector" title="통화 표시 단위 전환 (MTS 스타일)">
            <button
              type="button"
              className={`theme-btn ${currencyMode === 'KRW' ? 'active' : ''}`}
              onClick={() => onCurrencyModeChange && onCurrencyModeChange('KRW')}
              title="원화(₩) 기준 전체 합산 및 환산 표시"
            >
              <span>🇰🇷 원화(₩)</span>
            </button>
            <button
              type="button"
              className={`theme-btn ${currencyMode === 'USD' ? 'active' : ''}`}
              onClick={() => onCurrencyModeChange && onCurrencyModeChange('USD')}
              title="미국자산 순수 달러($) 표시 및 통화 분리 종합 집계"
            >
              <span>🇺🇸 달러($)</span>
            </button>
          </div>

          {/* Theme Selector */}
          <div className="theme-selector">
            <button
              className={`theme-btn ${currentTheme === 'dark' ? 'active' : ''}`}
              onClick={() => onThemeChange('dark')}
              title="다크 모드 (Dark Slate)"
            >
              <Moon size={14} />
              <span>다크</span>
            </button>
            <button
              className={`theme-btn ${currentTheme === 'light' ? 'active' : ''}`}
              onClick={() => onThemeChange('light')}
              title="라이트 모드 (Pure White)"
            >
              <Sun size={14} />
              <span>라이트</span>
            </button>
            <button
              className={`theme-btn ${currentTheme === 'sepia' ? 'active' : ''}`}
              onClick={() => onThemeChange('sepia')}
              title="세피아 모드 (Warm Beige)"
            >
              <Coffee size={14} />
              <span>세피아</span>
            </button>
          </div>

          {/* Exchange Rate Badge */}
          <div className="rate-badge-card">
            <DollarSign size={20} color="var(--color-safe)" />
            <div className="rate-info">
              <span className="rate-label">USD/KRW 환율 ({rateSource})</span>
              <span className="rate-value">{formatKRW(usdKrw)}</span>
            </div>
            <button 
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setCustomRate(usdKrw);
                setIsEditRateOpen(true);
              }}
              title="환율 수동 수정"
            >
              <Edit3 size={14} />
            </button>
          </div>

          {/* Refresh Prices Button */}
          <button 
            className="btn btn-secondary" 
            onClick={onRefresh} 
            disabled={refreshing}
            title="실시간 시세 및 환율 새로고침"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? '조회 중...' : '시세 새로고침'}
          </button>

          {/* Export CSV Backup Button */}
          <button 
            className="btn btn-secondary" 
            onClick={handleDownloadBackup}
            title="계좌, 자산, 잔고, 매매기록 CSV 압축 다운로드"
          >
            <Download size={16} />
            CSV 백업
          </button>
        </div>
      </div>

      {/* Edit Exchange Rate Modal */}
      {isEditRateOpen && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '440px' }}>
            <div className="modal-header">
              <h3 className="modal-title">💵 환율 수동 수정</h3>
              <button 
                className="btn btn-sm btn-secondary" 
                onClick={() => setIsEditRateOpen(false)}
              >
                ✕
              </button>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '16px' }}>
              필요에 따라 적용할 USD/KRW 환율을 직접 입력할 수 있습니다.
            </p>

            <div className="form-group">
              <label className="form-label">적용 환율 (원)</label>
              <input
                type="number"
                step="0.1"
                className="input-number"
                value={customRate}
                onChange={(e) => setCustomRate(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
              <button 
                className="btn btn-primary" 
                style={{ flex: 1 }}
                onClick={handleSaveRate}
                disabled={savingRate}
              >
                {savingRate ? '저장 중...' : '환율 적용'}
              </button>
              <button 
                className="btn btn-secondary"
                onClick={handleResetRate}
                disabled={savingRate}
              >
                실시간 환율로 초기화
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
