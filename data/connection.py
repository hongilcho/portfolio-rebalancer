"""One lazily-created thread-safe PostgreSQL pool and connection leases."""
import os
import threading
from psycopg2 import pool
from backend.config import SUPABASE_URL

_connection_pool = None
_pool_lock = threading.Lock()

def get_connection_pool():
    """
    PostgreSQL ThreadedConnectionPool 단일 인스턴스를 반환합니다. (스레드 안전)
    """
    global _connection_pool
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                pg_url = os.getenv("SUPABASE_URL") or SUPABASE_URL
                if not pg_url:
                    raise ValueError("SUPABASE_URL 환경 변수가 설정되지 않았습니다.")
                _connection_pool = pool.ThreadedConnectionPool(1, 20, pg_url)
    return _connection_pool


class PoolConnectionWrapper:
    """
    psycopg2 커넥션을 감싸는 래퍼 클래스
    
    Python Context Manager 프로토콜(__enter__, __exit__)을 지원하며,
    close() 호출 시 물리적 연결을 끊지 않고 풀(pool)로 안전하게 반납합니다.
    """
    def __init__(self, pool_obj, conn):
        self.pool = pool_obj
        self.conn = conn
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                self.rollback()
            except Exception:
                pass
        self.close()

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        # close 호출 시 진짜로 연결을 끊지 않고 풀에 반환 (중복 close 방지)
        if not self._closed:
            self._closed = True
            try:
                self.pool.putconn(self.conn)
            except Exception:
                pass


def get_connection(pool_provider=None) -> PoolConnectionWrapper:
    """
    커넥션 풀로부터 활성 PostgreSQL 연결을 대여하여 PoolConnectionWrapper로 반환합니다.
    with 구문과 함께 사용하는 것을 권장합니다.
    """
    pool_obj = (pool_provider or get_connection_pool)()
    conn = pool_obj.getconn()
    return PoolConnectionWrapper(pool_obj, conn)
