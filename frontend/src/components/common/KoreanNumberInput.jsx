/**
 * 한글 금액 단위 실시간 미리보기 숫자 입력 컴포넌트 (KoreanNumberInput.jsx)
 * ========================================================================
 * 큰 금액(원화) 입력 시 상단 라벨에 한글 단위(예: '1억 5,000만 원')를 실시간으로 표시하여
 * 사용자의 자릿수 입력 실수를 방지하는 특화 인풋 컴포넌트입니다.
 */

import React from 'react';
import { numToKrMixed } from '../../utils/formatters';

export default function KoreanNumberInput({
  label,
  value,
  onChange,
  step = 10000,
  min = 0,
  max,
  disabled = false,
  placeholder = '',
  className = ''
}) {
  const handleChange = (e) => {
    const val = parseFloat(e.target.value);
    onChange(isNaN(val) ? 0 : val);
  };

  const previewText = numToKrMixed(value);

  return (
    <div className={`form-group ${className}`}>
      {label && (
        <label className="form-label">
          {label} {value > 0 && <span className="helper-text">({previewText})</span>}
        </label>
      )}
      <div style={{ position: 'relative' }}>
        <input
          type="number"
          className="input-number"
          value={value === 0 && placeholder ? '' : value}
          onChange={handleChange}
          step={step}
          min={min}
          max={max}
          disabled={disabled}
          placeholder={placeholder}
        />
      </div>
    </div>
  );
}
