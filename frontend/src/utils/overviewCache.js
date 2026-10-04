// Separate the two asset scopes and invalidate results from old formulas.
export function createOverviewCache(storage) {
  try { storage ??= globalThis.sessionStorage; } catch {}
  const memory = new Map();
  const key = (includeCrypto) => `portfolio_overview_v2_${includeCrypto}`;
  return {
    get(includeCrypto) {
      if (memory.has(includeCrypto)) return memory.get(includeCrypto);
      try {
        const value = JSON.parse(storage?.getItem(key(includeCrypto)) || 'null');
        if (value?.include_crypto === includeCrypto && value.grand_total) {
          memory.set(includeCrypto, value);
          return value;
        }
      } catch { /* Missing or damaged browser storage is harmless. */ }
      return null;
    },
    set(includeCrypto, value) {
      if (value?.include_crypto !== includeCrypto) return;
      memory.set(includeCrypto, value);
      try { storage?.setItem(key(includeCrypto), JSON.stringify(value)); } catch {}
    },
  };
}
