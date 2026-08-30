import React, { useState, useEffect } from 'react';
import { X, Save, AlertCircle, Coins } from 'lucide-react';
import { formatKRW } from '../../utils/formatters';

export default function EditCryptoModal({ isOpen, onClose, initialHoldings, onSave }) {
  const [formData, setFormData] = useState({
    BTC: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' },
    ETH: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' }
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (initialHoldings && initialHoldings.length > 0) {
      const newForm = {
        BTC: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' },
        ETH: { quantity: 0, avg_price: 0, total_buy: 0, notes: '' }
      };

      initialHoldings.forEach(item => {
        const sym = item.symbol.toUpperCase();
        if (newForm[sym]) {
          const qty = Number(item.quantity) || 0;
          const avgP = Number(item.avg_price) || 0;
          newForm[sym] = {
            quantity: qty,
            avg_price: avgP,
            total_buy: qty * avgP,
            notes: item.notes || ''
          };
        }
      });
      setFormData(newForm);
    }
  }, [initialHoldings, isOpen]);

  if (!isOpen) return null;

  const handleQtyChange = (sym, qtyVal) => {
    const qty = parseFloat(qtyVal) || 0;
    setFormData(prev => {
      const curr = prev[sym];
      return {
        ...prev,
        [sym]: {
          ...curr,
          quantity: qtyVal,
          total_buy: qty > 0 && curr.avg_price > 0 ? qty * curr.avg_price : curr.total_buy
        }
      };
    });
  };

  const handleAvgPriceChange = (sym, avgPriceVal) => {
    const avgP = parseFloat(avgPriceVal) || 0;
    setFormData(prev => {
      const curr = prev[sym];
      const qty = parseFloat(curr.quantity) || 0;
      return {
        ...prev,
        [sym]: {
          ...curr,
          avg_price: avgPriceVal,
          total_buy: qty > 0 ? qty * avgP : 0
        }
      };
    });
  };

  const handleTotalBuyChange = (sym, totalBuyVal) => {
    const totalB = parseFloat(totalBuyVal) || 0;
    setFormData(prev => {
      const curr = prev[sym];
      const qty = parseFloat(curr.quantity) || 0;
      return {
        ...prev,
        [sym]: {
          ...curr,
          total_buy: totalBuyVal,
          avg_price: qty > 0 ? Math.round(totalB / qty) : curr.avg_price
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
          symbol: 'BTC',
          quantity: parseFloat(formData.BTC.quantity) || 0,
          avg_price: parseFloat(formData.BTC.avg_price) || 0,
          notes: formData.BTC.notes || ''
        },
        {
          symbol: 'ETH',
          quantity: parseFloat(formData.ETH.quantity) || 0,
          avg_price: parseFloat(formData.ETH.avg_price) || 0,
          notes: formData.ETH.notes || ''
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

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '580px', width: '92%' }} onClick={(e) => e.stopPropagation()}>
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

        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', background: 'var(--bg-surface)', padding: '10px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              💡 보유 수량(소수점 8자리 가능)과 매수 평단가를 입력해 주세요. (총 매입금액을 입력하시면 평단가가 자동 계산됩니다.)
            </div>

            {/* 1. Bitcoin Form */}
            <div style={{ background: 'rgba(245, 158, 11, 0.05)', border: '1px solid rgba(245, 158, 11, 0.25)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                <span style={{ fontSize: '1.1rem' }}>🪙</span>
                <strong style={{ fontSize: '1rem', color: '#F59E0B' }}>비트코인 (BTC)</strong>
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
                    value={formData.BTC.quantity}
                    onChange={(e) => handleQtyChange('BTC', e.target.value)}
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
                    value={formData.BTC.avg_price}
                    onChange={(e) => handleAvgPriceChange('BTC', e.target.value)}
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
                    value={formData.BTC.total_buy}
                    onChange={(e) => handleTotalBuyChange('BTC', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
              </div>

              {Number(formData.BTC.quantity) > 0 && (
                <div style={{ marginTop: '8px', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                  예상 매입금액: <strong style={{ color: 'var(--text-primary)' }}>{formatKRW(Number(formData.BTC.quantity) * Number(formData.BTC.avg_price))}</strong>
                </div>
              )}
            </div>

            {/* 2. Ethereum Form */}
            <div style={{ background: 'rgba(139, 92, 246, 0.05)', border: '1px solid rgba(139, 92, 246, 0.25)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                <span style={{ fontSize: '1.1rem' }}>💎</span>
                <strong style={{ fontSize: '1rem', color: '#8B5CF6' }}>이더리움 (ETH)</strong>
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
                    value={formData.ETH.quantity}
                    onChange={(e) => handleQtyChange('ETH', e.target.value)}
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
                    value={formData.ETH.avg_price}
                    onChange={(e) => handleAvgPriceChange('ETH', e.target.value)}
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
                    value={formData.ETH.total_buy}
                    onChange={(e) => handleTotalBuyChange('ETH', e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
              </div>

              {Number(formData.ETH.quantity) > 0 && (
                <div style={{ marginTop: '8px', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                  예상 매입금액: <strong style={{ color: 'var(--text-primary)' }}>{formatKRW(Number(formData.ETH.quantity) * Number(formData.ETH.avg_price))}</strong>
                </div>
              )}
            </div>
          </div>

          <div className="modal-footer" style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
              취소
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Save size={15} />
              {saving ? '저장 중...' : '저장하기'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
