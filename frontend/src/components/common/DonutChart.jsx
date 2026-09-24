import React, { useState, useMemo } from 'react';
import { formatKRW } from '../../utils/formatters';

// 세련된 기본 컬러 팔레트 (다크/라이트 모드 모두에 어울리는 색상군)
export const DEFAULT_PALETTE = [
  '#3B82F6', // Blue
  '#10B981', // Emerald
  '#F59E0B', // Amber
  '#8B5CF6', // Purple
  '#EC4899', // Pink
  '#06B6D4', // Cyan
  '#F97316', // Orange
  '#6366F1', // Indigo
  '#14B8A6', // Teal
  '#84CC16', // Lime
  '#A855F7', // Violet
  '#64748B', // Slate
];

/**
 * SVG 도넛 호(Arc) Path 문자열 생성 유틸리티
 */
function createArcPath(cx, cy, rInner, rOuter, startAngle, endAngle) {
  // 전체 원인 경우 (데이터가 1개)
  if (endAngle - startAngle >= 2 * Math.PI - 0.001) {
    return [
      `M ${cx} ${cy - rOuter}`,
      `A ${rOuter} ${rOuter} 0 1 0 ${cx} ${cy + rOuter}`,
      `A ${rOuter} ${rOuter} 0 1 0 ${cx} ${cy - rOuter}`,
      `M ${cx} ${cy - rInner}`,
      `A ${rInner} ${rInner} 0 1 1 ${cx} ${cy + rInner}`,
      `A ${rInner} ${rInner} 0 1 1 ${cx} ${cy - rInner}`,
      'Z'
    ].join(' ');
  }

  const x1 = cx + rOuter * Math.cos(startAngle);
  const y1 = cy + rOuter * Math.sin(startAngle);
  const x2 = cx + rOuter * Math.cos(endAngle);
  const y2 = cy + rOuter * Math.sin(endAngle);
  const x3 = cx + rInner * Math.cos(endAngle);
  const y3 = cy + rInner * Math.sin(endAngle);
  const x4 = cx + rInner * Math.cos(startAngle);
  const y4 = cy + rInner * Math.sin(startAngle);

  const largeArc = (endAngle - startAngle) > Math.PI ? 1 : 0;

  return [
    `M ${x1.toFixed(3)} ${y1.toFixed(3)}`,
    `A ${rOuter.toFixed(3)} ${rOuter.toFixed(3)} 0 ${largeArc} 1 ${x2.toFixed(3)} ${y2.toFixed(3)}`,
    `L ${x3.toFixed(3)} ${y3.toFixed(3)}`,
    `A ${rInner.toFixed(3)} ${rInner.toFixed(3)} 0 ${largeArc} 0 ${x4.toFixed(3)} ${y4.toFixed(3)}`,
    'Z'
  ].join(' ');
}

export default function DonutChart({
  data = [],
  title = '',
  centerLabel = '총 평가금액',
  centerValue = '',
  size = 240,
  innerRadiusRatio = 0.65,
  showLegend = true,
  legendMaxHeight = 220,
  colorPalette = DEFAULT_PALETTE,
  emptyMessage = '표시할 데이터가 없습니다.'
}) {
  const [hoveredIdx, setHoveredIdx] = useState(null);

  // 유효한 양수 데이터 필터링 및 정렬
  const processedData = useMemo(() => {
    const validItems = (data || [])
      .map((item, idx) => ({
        ...item,
        value: Math.max(0, Number(item.value) || 0),
        rawIndex: idx,
        color: item.color || colorPalette[idx % colorPalette.length]
      }))
      .filter(item => item.value > 0);

    const total = validItems.reduce((acc, cur) => acc + cur.value, 0);

    return {
      items: validItems.map(item => ({
        ...item,
        percent: total > 0 ? (item.value / total) * 100 : 0
      })),
      total
    };
  }, [data, colorPalette]);

  const { items, total } = processedData;

  // 도넛 차트 좌표 및 슬라이스 아크 계산
  const cx = size / 2;
  const cy = size / 2;
  const baseOuterR = (size / 2) - 10;
  const baseInnerR = baseOuterR * innerRadiusRatio;

  // 슬라이스 패스 정보 계산
  const slices = useMemo(() => {
    if (items.length === 0 || total <= 0) return [];

    const padAngle = items.length > 1 ? 0.02 : 0; // 슬라이스 간 틈새 (라디안)
    let currentAngle = -Math.PI / 2; // 12시 방향부터 시작

    return items.map((item, idx) => {
      const sliceAngle = (item.value / total) * (2 * Math.PI);
      const isHovered = hoveredIdx === idx;

      // 호버 시 살짝 확장
      const rOuter = isHovered ? baseOuterR + 4 : baseOuterR;
      const rInner = isHovered ? baseInnerR - 2 : baseInnerR;

      // 패딩 적용
      const startAngle = currentAngle + (padAngle / 2);
      const endAngle = currentAngle + sliceAngle - (padAngle / 2);
      currentAngle += sliceAngle;

      const path = createArcPath(cx, cy, rInner, rOuter, startAngle, endAngle);

      return {
        ...item,
        index: idx,
        path,
        isHovered
      };
    });
  }, [items, total, hoveredIdx, cx, cy, baseOuterR, baseInnerR]);

  // 현재 중앙에 표시할 텍스트
  const currentHovered = hoveredIdx !== null && items[hoveredIdx] ? items[hoveredIdx] : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', width: '100%' }}>
      {title && (
        <div style={{ 
          fontSize: '0.92rem', 
          fontWeight: 700, 
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}>
          {title}
        </div>
      )}

      {items.length === 0 || total <= 0 ? (
        <div style={{ 
          minHeight: `${size}px`, 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          background: 'var(--bg-surface)',
          borderRadius: 'var(--radius-md)',
          border: '1px dashed var(--border-color)',
          color: 'var(--text-muted)',
          fontSize: '0.85rem'
        }}>
          {emptyMessage}
        </div>
      ) : (
        <div style={{ 
          display: 'flex', 
          flexDirection: 'row', 
          alignItems: 'center', 
          justifyContent: 'center',
          gap: '24px',
          flexWrap: 'wrap'
        }}>
          {/* SVG Donut Chart */}
          <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
            <svg 
              width={size} 
              height={size} 
              viewBox={`0 0 ${size} ${size}`}
              style={{ overflow: 'visible', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.08))' }}
            >
              {slices.map((slice) => (
                <path
                  key={slice.label || slice.index}
                  d={slice.path}
                  fill={slice.color}
                  opacity={hoveredIdx === null || slice.isHovered ? 1 : 0.45}
                  style={{
                    cursor: 'pointer',
                    transition: 'all 0.2s ease-in-out',
                    transformOrigin: `${cx}px ${cy}px`,
                  }}
                  onMouseEnter={() => setHoveredIdx(slice.index)}
                  onMouseLeave={() => setHoveredIdx(null)}
                />
              ))}

              {/* 중앙 정보 텍스트 (SVG Text) */}
              <g 
                style={{ pointerEvents: 'none', userSelect: 'none' }}
                transform={`translate(${cx}, ${cy})`}
                textAnchor="middle"
              >
                {currentHovered ? (
                  <>
                    {/* 호버 시: 종목/라벨명 */}
                    <text
                      y="-16"
                      style={{
                        fontSize: '0.78rem',
                        fontWeight: 700,
                        fill: 'var(--text-secondary)'
                      }}
                    >
                      {currentHovered.label?.length > 12 
                        ? `${currentHovered.label.substring(0, 11)}...` 
                        : currentHovered.label}
                    </text>
                    {/* 호버 시: 금액 */}
                    <text
                      y="6"
                      style={{
                        fontSize: '0.98rem',
                        fontWeight: 800,
                        fill: 'var(--text-primary)'
                      }}
                    >
                      {formatKRW(currentHovered.value)}
                    </text>
                    {/* 호버 시: 비중 % */}
                    <text
                      y="26"
                      style={{
                        fontSize: '0.88rem',
                        fontWeight: 800,
                        fill: currentHovered.color
                      }}
                    >
                      {currentHovered.percent.toFixed(1)}%
                    </text>
                  </>
                ) : (
                  <>
                    {/* 기본 상태: 중앙 라벨 */}
                    <text
                      y="-12"
                      style={{
                        fontSize: '0.76rem',
                        fontWeight: 600,
                        fill: 'var(--text-muted)'
                      }}
                    >
                      {centerLabel}
                    </text>
                    {/* 기본 상태: 중앙 값 (총액) */}
                    <text
                      y="10"
                      style={{
                        fontSize: '0.98rem',
                        fontWeight: 800,
                        fill: 'var(--text-primary)'
                      }}
                    >
                      {centerValue || formatKRW(total)}
                    </text>
                    {/* 기본 상태: 100% 문구 */}
                    <text
                      y="28"
                      style={{
                        fontSize: '0.74rem',
                        fontWeight: 700,
                        fill: 'var(--accent-primary)'
                      }}
                    >
                      총 {items.length}개 항목
                    </text>
                  </>
                )}
              </g>
            </svg>
          </div>

          {/* Legend (우측 범례 리스트) */}
          {showLegend && (
            <div 
              style={{ 
                flex: 1, 
                minWidth: '200px', 
                maxWidth: '340px',
                maxHeight: `${legendMaxHeight}px`,
                overflowY: 'auto',
                display: 'flex', 
                flexDirection: 'column', 
                gap: '6px',
                paddingRight: '6px'
              }}
              className="custom-scrollbar"
            >
              {items.map((item, idx) => {
                const isItemHovered = hoveredIdx === idx;
                return (
                  <div
                    key={item.label || idx}
                    onMouseEnter={() => setHoveredIdx(idx)}
                    onMouseLeave={() => setHoveredIdx(null)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '4px 8px',
                      borderRadius: 'var(--radius-sm)',
                      background: isItemHovered ? 'var(--bg-surface)' : 'transparent',
                      border: isItemHovered ? '1px solid var(--border-color)' : '1px solid transparent',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      opacity: hoveredIdx === null || isItemHovered ? 1 : 0.5
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                      <span 
                        style={{ 
                          width: '10px', 
                          height: '10px', 
                          borderRadius: '50%', 
                          background: item.color,
                          flexShrink: 0
                        }} 
                      />
                      <span 
                        style={{ 
                          fontSize: '0.82rem', 
                          fontWeight: isItemHovered ? 700 : 500,
                          color: 'var(--text-primary)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis'
                        }}
                        title={item.label}
                      >
                        {item.label}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0, textAlign: 'right' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        {formatKRW(item.value)}
                      </span>
                      <span style={{ 
                        fontSize: '0.82rem', 
                        fontWeight: 700, 
                        color: item.color,
                        minWidth: '42px',
                        textAlign: 'right'
                      }}>
                        {item.percent.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
