/**
 * 숫자를 한국어 단위(만, 억, 조 등)로 변환하는 함수
 * @param {number} num
 * @returns {string} 예: "500만 원", "1억 2,000만 원", "0원"
 */
export function numToKrMixed(num) {
  if (!num || isNaN(num) || num === 0) {
    return '0원';
  }

  const isNegative = num < 0;
  let absNum = Math.floor(Math.abs(num));

  const units = ['', '만', '억', '조', '경'];
  const chunks = [];

  while (absNum > 0) {
    chunks.push(absNum % 10000);
    absNum = Math.floor(absNum / 10000);
  }

  let result = '';
  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    if (chunk > 0) {
      const chunkStr = chunk.toLocaleString('ko-KR');
      result = `${chunkStr}${units[i]} ${result}`.trim();
    }
  }

  const prefix = isNegative ? '-' : '';
  return `${prefix}${result} 원`.replace('  ', ' ').trim();
}

/**
 * 통화 단위 포맷터
 */
export function formatKRW(val) {
  if (val === null || val === undefined || isNaN(val)) return '0 원';
  const num = Math.round(Number(val));
  return `${num.toLocaleString('ko-KR')} 원`;
}

export function formatUSD(val) {
  if (val === null || val === undefined || isNaN(val)) return '$0.00';
  const num = Number(val);
  return `$${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatQuantity(val, unit = '주') {
  if (val === null || val === undefined || isNaN(val)) return `0 ${unit}`;
  const num = Number(val);
  if (Number.isInteger(num)) {
    return `${num.toLocaleString('ko-KR')} ${unit}`;
  }
  return `${num.toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} ${unit}`;
}

export function formatPercent(val, showSign = true) {
  if (val === null || val === undefined || isNaN(val)) return '0.0%';
  const num = Number(val);
  const sign = showSign && num > 0 ? '+' : '';
  return `${sign}${num.toFixed(1)}%`;
}
