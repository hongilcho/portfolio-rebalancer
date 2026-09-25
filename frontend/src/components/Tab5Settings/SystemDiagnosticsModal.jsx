import React, { useState, useEffect } from 'react';
import { Activity, RefreshCw, Copy, Check, X, Database, DollarSign, TrendingUp, Cpu } from 'lucide-react';
import { api } from '../../utils/api';

export default function SystemDiagnosticsModal({ isOpen, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const runBenchmark = async () => {
    setLoading(true);
    setError('');
    setCopied(false);
    try {
      const res = await api.getSystemBenchmark();
      setData(res);
    } catch (err) {
      console.error('Benchmark failed:', err);
      setError(err.message || '시스템 진단 요청 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      runBenchmark();
    } else {
      setData(null);
      setError('');
      setCopied(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCopyReport = () => {
    if (!data) return;

    const m = data.metrics || {};
    const db = m.database || {};
    const ex = m.exchange_rate || {};
    const kr = m.kr_stock_sample || {};
    const us = m.us_stock_sample || {};
    const cache = m.memory_cache || {};

    const report = `[배포 환경 성능 진단 리포트]
- 일시: ${data.timestamp}
- 환경: ${data.environment} (${data.platform || 'Linux/Render'})
- 진단 총 소요 시간: ${data.total_benchmark_time_sec}s
- 세부 통신 지연시간:
  * 🗄️ Database (${db.name || 'PostgreSQL'}): ${db.latency_ms !== null ? `${db.latency_ms}ms` : '실패'} (${db.status})
  * 💵 실시간 환율 (${ex.name || 'USD/KRW'}): ${ex.latency_ms !== null ? `${ex.latency_ms}ms` : '실패'} (수집처: ${ex.source}, 환율: ${ex.rate}원)
  * 🇰🇷 국내 주식 시세 (${kr.ticker}): ${kr.latency_ms !== null ? `${kr.latency_ms}ms` : '실패'} (수집처: ${kr.source})
  * 🇺🇸 미국 주식 시세 (${us.ticker}): ${us.latency_ms !== null ? `${us.latency_ms}ms` : '실패'} (수집처: ${us.source})
  * ⚡ 인메모리 캐시: ${cache.is_active ? `유효 (캐시 나이: ${cache.age_seconds}s, 항목: ${cache.cached_items_count}개)` : '캐시 없음/만료'}`;

    navigator.clipboard.writeText(report).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    });
  };

  const getLatencyBadge = (ms) => {
    if (ms === null || ms === undefined) {
      return <span style={{ color: '#EF4444', fontWeight: 600 }}>오류</span>;
    }
    const color = ms < 200 ? '#10B981' : ms < 800 ? '#F59E0B' : '#EF4444';
    return (
      <span style={{ color, fontWeight: 700, fontFamily: 'monospace' }}>
        {ms} ms
      </span>
    );
  };

  const metrics = data?.metrics || {};

  return (
    <div className="modal-overlay" style={{ zIndex: 1100 }}>
      <div className="modal-content" style={{ maxWidth: '640px', width: '92%' }}>
        {/* Modal Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={22} style={{ color: 'var(--accent-primary)' }} />
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>서버 통신 및 시세 수집 속도 진단</h3>
          </div>
          <button 
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
          >
            <X size={20} />
          </button>
        </div>

        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '0 0 16px 0', lineHeight: 1.5 }}>
          현재 배포 서버(Render)에서 데이터베이스(Supabase), 실시간 환율 및 주요 시세 API(네이버/NH)와의 통신 지연시간을 실시간으로 측정합니다.
        </p>

        {/* Loading State */}
        {loading && (
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            <RefreshCw size={28} className="animate-spin" style={{ margin: '0 auto 12px', color: 'var(--accent-primary)' }} />
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: 0 }}>
              서버 및 외부 시세 API 통신 상태를 측정 중입니다...
            </p>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div style={{ padding: '16px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #EF4444', borderRadius: '8px', color: '#EF4444', fontSize: '13px', marginBottom: '16px' }}>
            {error}
          </div>
        )}

        {/* Results */}
        {data && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Environment Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--bg-secondary)', borderRadius: '8px', fontSize: '12px' }}>
              <span style={{ color: 'var(--text-secondary)' }}>
                <strong>환경:</strong> {data.environment} ({data.platform?.split('-')[0] || 'Cloud'})
              </span>
              <span style={{ color: 'var(--text-secondary)' }}>
                <strong>총 진단 시간:</strong> <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{data.total_benchmark_time_sec}초</span>
              </span>
            </div>

            {/* Metrics List */}
            <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', padding: '10px 14px', background: 'var(--bg-secondary)', fontWeight: 600, fontSize: '12px', borderBottom: '1px solid var(--border-color)' }}>
                <span>측정 항목</span>
                <span>응답 속도</span>
                <span>수집 출처 / 상태</span>
              </div>

              {/* DB */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', padding: '12px 14px', alignItems: 'center', fontSize: '13px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Database size={15} style={{ color: '#3B82F6' }} />
                  {metrics.database?.name || 'Supabase PostgreSQL'}
                </span>
                <span>{getLatencyBadge(metrics.database?.latency_ms)}</span>
                <span style={{ fontSize: '12px', color: metrics.database?.status === '정상' ? '#10B981' : '#EF4444' }}>
                  {metrics.database?.status}
                </span>
              </div>

              {/* Exchange Rate */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', padding: '12px 14px', alignItems: 'center', fontSize: '13px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <DollarSign size={15} style={{ color: '#10B981' }} />
                  실시간 USD/KRW 환율
                </span>
                <span>{getLatencyBadge(metrics.exchange_rate?.latency_ms)}</span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {metrics.exchange_rate?.source} ({metrics.exchange_rate?.rate}원)
                </span>
              </div>

              {/* KR Stock */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', padding: '12px 14px', alignItems: 'center', fontSize: '13px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <TrendingUp size={15} style={{ color: '#F59E0B' }} />
                  국내 주식 ({metrics.kr_stock_sample?.ticker?.split(' ')[0]})
                </span>
                <span>{getLatencyBadge(metrics.kr_stock_sample?.latency_ms)}</span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {metrics.kr_stock_sample?.source}
                </span>
              </div>

              {/* US Stock */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', padding: '12px 14px', alignItems: 'center', fontSize: '13px', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <TrendingUp size={15} style={{ color: '#8B5CF6' }} />
                  미국 주식 ({metrics.us_stock_sample?.ticker?.split(' ')[0]})
                </span>
                <span>{getLatencyBadge(metrics.us_stock_sample?.latency_ms)}</span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {metrics.us_stock_sample?.source}
                </span>
              </div>

              {/* Cache */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', padding: '12px 14px', alignItems: 'center', fontSize: '13px' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Cpu size={15} style={{ color: '#06B6D4' }} />
                  인메모리 캐시 상태
                </span>
                <span style={{ fontSize: '12px', color: metrics.memory_cache?.is_active ? '#10B981' : '#F59E0B', fontWeight: 600 }}>
                  {metrics.memory_cache?.is_active ? '유효 (Active)' : '캐시 없음/만료'}
                </span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {metrics.memory_cache?.is_active ? `${metrics.memory_cache?.age_seconds}초 경과 (${metrics.memory_cache?.cached_items_count}개)` : '다음 조회 시 신규 갱신'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Modal Actions */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-color)' }}>
          <button
            className="btn btn-secondary"
            onClick={runBenchmark}
            disabled={loading}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            <span>다시 진단하기</span>
          </button>

          <div style={{ display: 'flex', gap: '10px' }}>
            {data && (
              <button
                className="btn btn-primary"
                onClick={handleCopyReport}
                style={{ 
                  display: 'inline-flex', 
                  alignItems: 'center', 
                  gap: '6px', 
                  fontSize: '13px',
                  backgroundColor: copied ? '#10B981' : 'var(--accent-primary)',
                  borderColor: copied ? '#10B981' : 'var(--accent-primary)'
                }}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? '리포트 복사됨!' : 'AI 전달용 리포트 복사'}</span>
              </button>
            )}
            <button className="btn btn-secondary" onClick={onClose} style={{ fontSize: '13px' }}>
              닫기
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
