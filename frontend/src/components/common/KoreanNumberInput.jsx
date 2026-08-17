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
  suffix = '원',
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
