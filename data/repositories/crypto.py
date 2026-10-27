"""Crypto holdings persistence by owner and symbol."""
from datetime import datetime
from typing import Optional
from psycopg2.extras import RealDictCursor
from data.repository_context import RepositoryContext
from logic.crypto_numbers import precise_holding

def get_crypto_holdings(db: RepositoryContext, owner: Optional[str] = None):
    conn = db.connect()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if owner:
            cursor.execute("SELECT c.*,c.quantity::double precision AS quantity_precise,c.avg_price::double precision AS avg_price_precise FROM crypto_holdings c WHERE owner = %s ORDER BY symbol ASC", (owner,))
        else:
            cursor.execute("SELECT c.*,c.quantity::double precision AS quantity_precise,c.avg_price::double precision AS avg_price_precise FROM crypto_holdings c ORDER BY owner ASC, symbol ASC")
        rows = cursor.fetchall()
        return [precise_holding(r) for r in rows]
    except Exception as e:
        print(f"Error fetching crypto holdings: {e}")
        return []
    finally:
        conn.close()


def save_crypto_holding(
    db: RepositoryContext,
    symbol: str,
    quantity: float,
    avg_price: float,
    owner: str='홍일',
    notes: str='',
):
    conn = db.connect()
    cursor = conn.cursor()
    owner_clean = owner.strip() if owner else "홍일"
    sym_clean = symbol.strip().upper()
    owner_tag = "hongil" if owner_clean == "홍일" else ("yoona" if owner_clean == "윤아" else owner_clean.lower())
    record_id = f"crypto_{owner_tag}_{sym_clean.lower()}"
    coin_name = '비트코인' if sym_clean == 'BTC' else ('이더리움' if sym_clean == 'ETH' else sym_clean)

    try:
        from data.repositories import crypto_history
        crypto_history.lock(cursor)
        cursor.execute('''
            INSERT INTO crypto_holdings (id, owner, symbol, name, quantity, avg_price, notes, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (owner, symbol) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                avg_price = EXCLUDED.avg_price,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
        ''', (
            record_id,
            owner_clean,
            sym_clean,
            coin_name,
            max(0.0, float(quantity)),
            max(0.0, float(avg_price)),
            notes or "",
            datetime.now()
        ))
        # Same transaction as the existing edit; past valuations stay frozen.
        # RealDictCursor is required by the private history journal reader.
        history_cursor=conn.cursor(cursor_factory=RealDictCursor)
        try:crypto_history.changed(history_cursor,db)
        finally:history_cursor.close()
        conn.commit()
        return True, f"[{owner_clean}] {sym_clean} 보유 정보가 성공적으로 저장되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
