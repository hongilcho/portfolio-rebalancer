import React from 'react';
import { RefreshCw, X } from 'lucide-react';

export default function ViewLoading() {
  return (
    <div className="section-card" role="status" style={{ textAlign: 'center', padding: '60px 20px' }}>
      <RefreshCw size={32} className="animate-spin" style={{ margin: '0 auto 16px', color: 'var(--accent-primary)' }} />
      <p style={{ color: 'var(--text-secondary)' }}>화면을 불러오는 중입니다...</p>
    </div>
  );
}

export function DialogLoading({ onClose }) {
  return (
    <div className="modal-overlay">
      <div className="modal-content" role="dialog" aria-modal="true" aria-label="화면 불러오기" style={{ maxWidth: '420px' }}>
        <button className="btn btn-secondary btn-sm" aria-label="닫기" onClick={onClose} style={{ float: 'right' }}>
          <X size={18} />
        </button>
        <ViewLoading />
      </div>
    </div>
  );
}
