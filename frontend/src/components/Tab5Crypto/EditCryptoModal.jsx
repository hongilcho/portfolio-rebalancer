/**
 * 가상자산 보유량 및 평단가 수정 모달 (EditCryptoModal.jsx)
 * ========================================================
 * 소유자별(홍일, 윤아) 비트코인 및 이더리움의 보유 수량, 매입 평단가 및 비고 메모를 편집합니다.
 */

import React, { useState, useEffect } from 'react';
import { X, Save, Coins } from 'lucide-react';
import { formatKRW } from '../../utils/formatters';

export default function EditCryptoModal({ isOpen, onClose, byOwner, onSave }) {
  const [activeTab, setActiveTab] = useState('hongil'); // 'hongil' | 'yoona'
  const [formData, setFormData] = useState({
    hongil: {
      BTC: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' },
      ETH: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' }
    },
    yoona: {
      BTC: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' },
      ETH: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' }
    }
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (byOwner && isOpen) {
      const newForm = {
        hongil: {
          BTC: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' },
          ETH: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' }
        },
        yoona: {
          BTC: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' },
          ETH: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' }
        }
      };

      const setOwnerAssets = (ownerKey, ownerName) => {
        const oData = byOwner[ownerName];
        if (oData && oData.assets) {
          oData.assets.forEach(item => {
            const sym = item.symbol.toUpperCase();
            if (newForm[ownerKey][sym]) {
              const qty = Number(item.quantity) || 0;
              const avgP = Number(item.avg_price) || 0;
              newForm[ownerKey][sym] = {
                quantity: qty,
                avg_price: avgP,
                total_buy: qty * avgP,
                notes: item.notes || ''
              };
            }
          });
        }
      };

      setOwnerAssets('hongil', '홍일');
      setOwnerAssets('yoona', '윤아');
      setFormData(newForm);
    }
  }, [byOwner, isOpen]);

  if (!isOpen) return null;

  const handleQtyChange = (ownerKey, sym, qtyVal) => {
    const qty = parseFloat(qtyVal) || 0;
    setFormData(prev => {
      const curr = prev[ownerKey][sym];
      return {
        ...prev,
        [ownerKey]: {
          ...prev[ownerKey],
          [sym]: {
            ...curr,
            quantity: qtyVal,
            total_buy: qty > 0 && curr.avg_price > 0 ? qty * curr.avg_price : curr.total_buy
          }
        }
      };
    });
  };

  const handleAvgPriceChange = (ownerKey, sym, avgPriceVal) => {
    const avgP = parseFloat(avgPriceVal) || 0;
    setFormData(prev => {
      const curr = prev[ownerKey][sym];
      const qty = parseFloat(curr.quantity) || 0;
      return {
        ...prev,
        [ownerKey]: {
          ...prev[ownerKey],
          [sym]: {
            ...curr,
            avg_price: avgPriceVal,
            total_buy: qty > 0 ? qty * avgP : 0
          }
        }
      };
    });
  };

  const handleTotalBuyChange = (ownerKey, sym, totalBuyVal) => {
    const totalB = parseFloat(totalBuyVal) || 0;
    setFormData(prev => {
      const curr = prev[ownerKey][sym];
      const qty = parseFloat(curr.quantity) || 0;
      return {
        ...prev,
        [ownerKey]: {
          ...prev[ownerKey],
          [sym]: {
            ...curr,
            total_buy: totalBuyVal,
            avg_price: qty > 0 ? Math.round(totalB / qty) : curr.avg_price
          }
        }
      };
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = [
        {
          owner: '홍일',
          symbol: 'BTC',
          quantity: parseFloat(formData.hongil.BTC.quantity) || 0,
          avg_price: parseFloat(formData.hongil.BTC.avg_price) || 0,
          notes: formData.hongil.BTC.notes || ''
        },
        {
          owner: '홍일',
          symbol: 'ETH',
          quantity: parseFloat(formData.hongil.ETH.quantity) || 0,
          avg_price: parseFloat(formData.hongil.ETH.avg_price) || 0,
          notes: formData.hongil.ETH.notes || ''
        },
        {
          owner: '윤아',
          symbol: 'BTC',
          quantity: parseFloat(formData.yoona.BTC.quantity) || 0,
          avg_price: parseFloat(formData.yoona.BTC.avg_price) || 0,
          notes: formData.yoona.BTC.notes || ''
        },
        {
          owner: '윤아',
          symbol: 'ETH',
          quantity: parseFloat(formData.yoona.ETH.quantity) || 0,
          avg_price: parseFloat(formData.yoona.ETH.avg_price) || 0,
          notes: formData.yoona.ETH.notes || ''
        }
      ];
      await onSave(payload);
      onClose();
    } catch (err) {
      alert(`저장 실패: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const currentForm = formData[activeTab];
  const ownerLabel = activeTab === 'hongil' ? '홍일' : '윤아';
  const ownerIcon = activeTab === 'hongil' ? '👨' : '👩';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '620px', width: '92%' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Coins size={20} color="#F59E0B" />
            <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 700 }}>
              가상화폐(BTC / ETH) 보유 정보 수정
            </h3>
          </div>
          <button className="btn-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Owner Tab Switcher */}
        <div style={{ display: 'flex', gap: '8px', padding: '14px 20px 0', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-surface)' }}>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'hongil' ? 'active' : ''}`}
            onClick={() => setActiveTab('hongil')}
            style={{
              padding: '10px 16px',
              border: 'none',
              background: 'none',
              fontWeight: activeTab === 'hongil' ? 800 : 500,
              color: activeTab === 'hongil' ? '#0EA5E9' : 'var(--text-secondary)',
              borderBottom: activeTab === 'hongil' ? '2px solid #0EA5E9' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.95rem'
            }}
          >
            <span>👨</span> 홍일 계정 (업비트)
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'yoona' ? 'active' : ''}`}
            onClick={() => setActiveTab('yoona')}
            style={{
              padding: '10px 16px',
              border: 'none',
              background: 'none',
              fontWeight: activeTab === 'yoona' ? 800 : 500,
              color: activeTab === 'yoona' ? '#EC4899' : 'var(--text-secondary)',
              borderBottom: activeTab === 'yoona' ? '2px solid #EC4899' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.95rem'
            }}
          >
            <span>👩</span> 윤아 계정 (업비트)
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '18px', padding: '20px' }}>
            <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', background: 'var(--bg-surface)', padding: '10px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              💡 <strong>{ownerIcon} {ownerLabel}</strong> 님의 보유 수량(소수점 8자리 가능)과 매수 평단가를 입력해 주세요. (총 매입액 입력 시 평단가 자동 계산)
            </div>

            {/* 1. Bitcoin Form */}
            <div style={{ background: 'rgba(245, 158, 11, 0.05)', border: '1px solid rgba(245, 158, 11, 0.25)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                <span style={{ fontSize: '1.1rem' }}>🪙</span>
                <strong style={{ fontSize: '1rem', color: '#F59E0B' }}>비트코인 (BTC)</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>- {ownerLabel} 보유분</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    보유 수량 (BTC)
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    placeholder="예: 0.1542"
                    className="input-text"
                    value={currentForm.BTC.quantity}
                    onChange={(e) => handleQtyChange(activeTab, 'BTC', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    매수 평단가 (원)
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    placeholder="예: 85000000"
                    className="input-text"
                    value={currentForm.BTC.avg_price}
                    onChange={(e) => handleAvgPriceChange(activeTab, 'BTC', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    총 매입금액 (원)
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    placeholder="총 매입액"
                    className="input-text"
                    value={currentForm.BTC.total_buy}
                    onChange={(e) => handleTotalBuyChange(activeTab, 'BTC', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
              </div>

              {Number(currentForm.BTC.quantity) > 0 && (
                <div style={{ marginTop: '8px', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                  예상 매입금액: <strong style={{ color: 'var(--text-primary)' }}>{formatKRW(Number(currentForm.BTC.quantity) * Number(currentForm.BTC.avg_price))}</strong>
                </div>
              )}
            </div>

            {/* 2. Ethereum Form */}
            <div style={{ background: 'rgba(139, 92, 246, 0.05)', border: '1px solid rgba(139, 92, 246, 0.25)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                <span style={{ fontSize: '1.1rem' }}>💎</span>
                <strong style={{ fontSize: '1rem', color: '#8B5CF6' }}>이더리움 (ETH)</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>- {ownerLabel} 보유분</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    보유 수량 (ETH)
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    placeholder="예: 2.5"
                    className="input-text"
                    value={currentForm.ETH.quantity}
                    onChange={(e) => handleQtyChange(activeTab, 'ETH', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    매수 평단가 (원)
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    placeholder="예: 4200000"
                    className="input-text"
                    value={currentForm.ETH.avg_price}
                    onChange={(e) => handleAvgPriceChange(activeTab, 'ETH', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    총 매입금액 (원)
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    placeholder="총 매입액"
                    className="input-text"
                    value={currentForm.ETH.total_buy}
                    onChange={(e) => handleTotalBuyChange(activeTab, 'ETH', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
              </div>

              {Number(currentForm.ETH.quantity) > 0 && (
                <div style={{ marginTop: '8px', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                  예상 매입금액: <strong style={{ color: 'var(--text-primary)' }}>{formatKRW(Number(currentForm.ETH.quantity) * Number(currentForm.ETH.avg_price))}</strong>
                </div>
              )}
            </div>
          </div>

          <div className="modal-footer" style={{ marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderTop: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              * '저장하기'를 누르면 홍일 님과 윤아 님의 설정이 일괄 반영됩니다.
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
                취소
              </button>
              <button type="submit" className="btn btn-primary" disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Save size={15} />
                {saving ? '저장 중...' : '전체 저장하기'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
