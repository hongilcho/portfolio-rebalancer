"""Persistent market/dividend cache JSONB IO; cache policy stays with callers."""
import json
from typing import Optional, Any, Tuple
from data.repository_context import RepositoryContext

def save_market_cache(db: RepositoryContext, key: str, data: Any) -> bool:
    """
    지속성 시장 데이터/시세/환율 캐시 저장 (JSONB 포맷)
    PostgreSQL의 market_cache 테이블에 저장하여 서버 재시작 및 배포 후에도 즉시 복구 가능하게 함.
    """
    conn = db.connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO market_cache (key, data, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE
            SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
        """, (key, json.dumps(data)))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving market cache for {key}: {e}")
        return False
    finally:
        conn.close()


def get_market_cache(db: RepositoryContext, key: str) -> Tuple[Optional[Any], float]:
    """
    지속성 시장 데이터/시세/환율 캐시 조회
    Returns:
        (data, age_in_seconds): 캐시 데이터와 생성 후 경과 시간(초). 없으면 (None, 999999.0)
    """
    conn = db.connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT data, EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - updated_at)) as age_seconds
            FROM market_cache WHERE key = %s
        """, (key,))
        row = cursor.fetchone()
        if row:
            raw_data = row[0]
            parsed = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            age = float(row[1]) if row[1] is not None else 0.0
            return parsed, age
    except Exception as e:
        print(f"Error getting market cache for {key}: {e}")
    finally:
        conn.close()
    return None, 999999.0
