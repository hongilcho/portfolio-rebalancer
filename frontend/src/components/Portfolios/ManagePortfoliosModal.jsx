import React, { useState } from 'react';
import { X, Plus, Edit3, Trash2, Check, FolderPlus, Briefcase, AlertCircle } from 'lucide-react';
import { api } from '../../utils/api';

export default function ManagePortfoliosModal({ 
  isOpen, 
  onClose, 
  portfolios, 
  currentPortfolioId, 
  onSelectPortfolio, 
  onRefresh 
}) {
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleStartEdit = (p) => {
    setEditingId(p.id);
    setEditName(p.name);
    setEditDesc(p.description || '');
    setError('');
  };

  const handleSaveEdit = async (id) => {
    if (!editName.trim()) {
      setError('포트폴리오 이름을 입력해주세요.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await api.updatePortfolio(id, editName.trim(), editDesc.trim());
      setEditingId(null);
      await onRefresh();
    } catch (err) {
      setError(err.message || '포트폴리오 수정 실패');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newName.trim()) {
      setError('새 포트폴리오 이름을 입력해주세요.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await api.createPortfolio(newName.trim(), newDesc.trim());
      setNewName('');
      setNewDesc('');
      setIsCreating(false);
      await onRefresh();
      if (res?.portfolio?.id) {
        onSelectPortfolio(res.portfolio.id);
      }
    } catch (err) {
      setError(err.message || '포트폴리오 생성 실패');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (p) => {
    if (p.is_default) {
      alert('기본 포트폴리오는 삭제할 수 없습니다.');
      return;
    }
    if (!window.confirm(`'${p.name}' 포트폴리오를 정말로 삭제하시겠습니까?\n포트폴리오에 등록된 계좌나 종목이 있는 경우 삭제할 수 없습니다.`)) {
      return;
    }
    setLoading(true);
    setError('');
    try {
      await api.deletePortfolio(p.id);
      if (currentPortfolioId === p.id) {
        onSelectPortfolio('default');
      }
      await onRefresh();
    } catch (err) {
      setError(err.message || '포트폴리오 삭제 실패');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '620px', width: '92%' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Briefcase size={20} color="var(--accent-primary)" />
            <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700 }}>
              포트폴리오 관리 및 설정
            </h3>
          </div>
          <button className="btn-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', background: 'var(--bg-surface)', padding: '10px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
            💡 각 포트폴리오의 이름과 운용 전략(설명/메모)을 관리하고, 새로운 독립 포트폴리오를 추가할 수 있습니다.
          </div>

          {error && (
            <div className="alert-banner alert-danger" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Portfolios List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong style={{ fontSize: '0.92rem' }}>등록된 포트폴리오 목록 ({portfolios.length}개)</strong>
              {!isCreating && (
                <button 
                  className="btn btn-primary btn-sm" 
                  onClick={() => setIsCreating(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Plus size={14} />
                  새 포트폴리오 추가
                </button>
              )}
            </div>

            {/* Create New Form */}
            {isCreating && (
              <form onSubmit={handleCreate} style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--accent-primary)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <strong style={{ fontSize: '0.9rem', color: 'var(--accent-primary)' }}>✨ 신규 포트폴리오 생성</strong>
                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    포트폴리오 이름 *
                  </label>
                  <input
                    type="text"
                    className="input-text"
                    placeholder="예: 아내 은퇴포트폴리오, 자녀 자산 등"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    style={{ width: '100%' }}
                    autoFocus
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    운용 전략 및 개략적 설명 (메모)
                  </label>
                  <input
                    type="text"
                    className="input-text"
                    placeholder="예: 미국 지수 ETF 및 배당성장 포트폴리오"
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '4px' }}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setIsCreating(false)}>
                    취소
                  </button>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={loading}>
                    {loading ? '생성 중...' : '생성 완료'}
                  </button>
                </div>
              </form>
            )}

            {/* Existing Portfolios Cards */}
            {portfolios.map((p) => {
              const isEditing = editingId === p.id;
              const isSelected = currentPortfolioId === p.id;

              return (
                <div 
                  key={p.id}
                  style={{
                    background: 'var(--bg-card)',
                    border: isSelected ? '2px solid var(--accent-primary)' : '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-md)',
                    padding: '14px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px'
                  }}
                >
                  {isEditing ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <input
                        type="text"
                        className="input-text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="포트폴리오 이름"
                      />
                      <input
                        type="text"
                        className="input-text"
                        value={editDesc}
                        onChange={(e) => setEditDesc(e.target.value)}
                        placeholder="설명 및 메모"
                      />
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                        <button className="btn btn-secondary btn-sm" onClick={() => setEditingId(null)}>
                          취소
                        </button>
                        <button className="btn btn-primary btn-sm" onClick={() => handleSaveEdit(p.id)} disabled={loading}>
                          저장
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <strong style={{ fontSize: '1rem', color: isSelected ? 'var(--accent-primary)' : 'inherit' }}>
                            {p.name}
                          </strong>
                          {p.is_default && (
                            <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                              기본 포트폴리오
                            </span>
                          )}
                          {isSelected && (
                            <span className="badge" style={{ background: 'var(--accent-primary)', color: '#fff', fontSize: '0.7rem' }}>
                              현재 선택됨
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
                          {p.description || '(등록된 메모 없음)'}
                        </p>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {!isSelected && (
                          <button 
                            className="btn btn-secondary btn-sm"
                            onClick={() => {
                              onSelectPortfolio(p.id);
                              onClose();
                            }}
                          >
                            전환하기
                          </button>
                        )}
                        <button 
                          className="btn btn-secondary btn-sm" 
                          onClick={() => handleStartEdit(p)}
                          title="이름 및 설명 수정"
                        >
                          <Edit3 size={13} />
                        </button>
                        {!p.is_default && (
                          <button 
                            className="btn btn-secondary btn-sm" 
                            onClick={() => handleDelete(p)}
                            title="포트폴리오 삭제"
                            style={{ color: 'var(--color-loss)' }}
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="modal-footer" style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
