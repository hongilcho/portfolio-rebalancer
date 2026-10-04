/** PriceReference: presentation only; state and API actions stay in the parent. */
import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { formatKRW, formatUSD } from '../../utils/formatters';

export default function PriceReference({
  setIsPriceRefOpen,
  isPriceRefOpen,
  assets,
  usdPriceMap,
  priceMap,
  usdKrw,
}) {
  return (
    <>
      {/* 1. Price Reference Collapsible */}
      <div className="section-card" style={{ padding: '16px 20px', marginBottom: '16px' }}>
        <div
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
          onClick={() => setIsPriceRefOpen(!isPriceRefOpen)}
        >
          <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>💡 실시간 시세 참고표 (현재가 확인용)</span>
          {isPriceRefOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>

        {isPriceRefOpen && (
          <div className="table-container" style={{ marginTop: '14px' }}>
            <table className="custom-table">
              <thead>
                <tr>
                  <th>종목명</th>
                  <th>티커</th>
                  <th>시장</th>
                  <th>실시간 현재가</th>
                  <th>원화 환산가</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((ast) => {
                  const isUS = ast.market === 'US';
                  const usdP = usdPriceMap[String(ast.id)] || (priceMap[String(ast.id)] ? Number((priceMap[String(ast.id)] / (usdKrw || 1380)).toFixed(2)) : 0);
                  const krwP = priceMap[String(ast.id)] || 0;
                  return (
                    <tr key={ast.id}>
                      <td style={{ fontWeight: 600 }}>{isUS ? '🇺🇸 ' : '🇰🇷 '}{ast.name}</td>
                      <td>{ast.ticker}</td>
                      <td>{isUS ? '미국 (USD)' : '국내 (KRW)'}</td>
                      <td style={{ fontWeight: 700 }}>
                        {isUS ? formatUSD(usdP) : formatKRW(krwP)}
                      </td>
                      <td style={{ fontWeight: 600, color: isUS ? 'var(--text-secondary)' : 'inherit' }}>
                        {formatKRW(krwP)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
