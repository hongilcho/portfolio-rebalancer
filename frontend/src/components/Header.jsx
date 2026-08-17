import React, { useState } from 'react';
import { RefreshCw, Download, Edit3, DollarSign, TrendingUp, Moon, Sun, Coffee } from 'lucide-react';
import { api } from '../utils/api';
import { formatKRW } from '../utils/formatters';

export default function Header({ 
  usdKrw, 
  rateSource, 
  onRefresh, 
  refreshing,
  currentTheme,
  onThemeChange
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

        <div className="header-controls">
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
