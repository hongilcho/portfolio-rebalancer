import React, { useState } from 'react';
import { Lock, ArrowRight } from 'lucide-react';
import { api } from '../utils/api';

export default function AuthModal({ onAuthenticated }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password) return;

    setLoading(true);
    setError('');

    try {
      await api.verifyPassword(password);
      localStorage.setItem('portfolio_auth', 'true');
      onAuthenticated();
    } catch (err) {
      setError(err.message || '비밀번호가 일치하지 않습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '420px', textAlign: 'center' }}>
        <div style={{ display: 'inline-flex', padding: '16px', background: 'rgba(99, 102, 241, 0.1)', borderRadius: '50%', marginBottom: '16px' }}>
          <Lock size={32} color="var(--accent-primary)" />
        </div>
        
        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: '8px' }}>
          포트폴리오 매니저 로그인
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '24px' }}>
          보안 접속을 위해 설정된 암호를 입력해 주세요.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group" style={{ textAlign: 'left' }}>
            <input
              type="password"
              className="input-text"
              placeholder="비밀번호 입력"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
            />
          </div>

          {error && (
            <div className="alert-banner alert-danger" style={{ textAlign: 'left', marginBottom: '16px' }}>
              {error}
            </div>
          )}

          <button 
            type="submit" 
            className="btn btn-primary btn-block" 
            disabled={loading}
            style={{ padding: '12px', fontSize: '1rem' }}
          >
            {loading ? '인증 중...' : '접속하기'} <ArrowRight size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}
