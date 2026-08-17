import React from 'react';

export default function DriftBar({ drift, scaleMax = 1.0 }) {
  const isPositive = drift > 0;
  const isNegative = drift < 0;
  const absDrift = Math.abs(drift);
  
  // Calculate width in pixels relative to half-width (90px)
  const maxPx = 90;
  const clampedScale = scaleMax > 0 ? scaleMax : 1.0;
  const widthPx = Math.min(maxPx, Math.round((absDrift / clampedScale) * maxPx));
  
  const formattedDrift = `${isPositive ? '+' : ''}${drift.toFixed(1)}%`;
  const colorClass = isPositive ? 'var(--color-profit)' : isNegative ? 'var(--color-loss)' : 'var(--text-muted)';

  return (
    <div className="drift-bar-container">
      <div className="drift-label" style={{ color: colorClass }}>
        {formattedDrift}
      </div>
      <div className="drift-track">
        <div className="drift-center-line" />
        {isPositive && (
          <div 
            className="drift-bar-fill positive" 
            style={{ width: `${widthPx}px` }} 
          />
        )}
        {isNegative && (
          <div 
            className="drift-bar-fill negative" 
            style={{ width: `${widthPx}px` }} 
          />
        )}
      </div>
      <div className="drift-ticks">
        <span>-{clampedScale.toFixed(1)}%</span>
        <span>0</span>
        <span>+{clampedScale.toFixed(1)}%</span>
      </div>
    </div>
  );
}
