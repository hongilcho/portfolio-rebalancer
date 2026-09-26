import React from 'react';
import { AlertTriangle, RefreshCw, Trash2 } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary caught error]', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleClearCacheAndReload = () => {
    try {
      sessionStorage.clear();
    } catch {}
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px',
          background: 'var(--bg-primary, #0B0F19)',
          color: 'var(--text-primary, #F8FAFC)'
        }}>
          <div style={{
            maxWidth: '520px',
            width: '100%',
            background: 'var(--bg-surface, #1E293B)',
            border: '1px solid var(--border-color, #334155)',
            borderRadius: '16px',
            padding: '32px',
            textAlign: 'center',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)'
          }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: 'rgba(239, 68, 68, 0.15)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '16px'
            }}>
              <AlertTriangle size={32} color="#EF4444" />
            </div>

            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '8px' }}>
              화면을 불러오는 중 오류가 발생했습니다
            </h2>
            <p style={{ color: 'var(--text-secondary, #94A3B8)', fontSize: '0.88rem', marginBottom: '20px', lineHeight: 1.5 }}>
              일시적인 렌더링 오류가 감지되었습니다. 아래 버튼을 통해 새로고침하거나 캐시를 초기화하여 복구할 수 있습니다.
            </p>

            {this.state.error && (
              <div style={{
                background: 'rgba(0, 0, 0, 0.3)',
                padding: '12px 14px',
                borderRadius: '8px',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                fontSize: '0.78rem',
                color: '#F87171',
                textAlign: 'left',
                marginBottom: '24px',
                overflowX: 'auto',
                fontFamily: 'monospace'
              }}>
                {String(this.state.error.message || this.state.error)}
              </div>
            )}

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={this.handleReload}
                className="btn btn-primary"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '10px 18px', fontSize: '0.9rem' }}
              >
                <RefreshCw size={16} /> 새로고침
              </button>
              <button
                type="button"
                onClick={this.handleClearCacheAndReload}
                className="btn btn-secondary"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '10px 18px', fontSize: '0.9rem' }}
              >
                <Trash2 size={16} /> 캐시 초기화 후 재접속
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
