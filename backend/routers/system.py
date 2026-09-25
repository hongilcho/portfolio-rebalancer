"""
시스템 성능 진단 및 벤치마크 API 라우터 (System Diagnostics Router)
===================================================================
데이터베이스 핑, 실시간 환율 수집 속도, 국내/미국 주식 시세 API 응답속도,
인메모리 캐시 상태 및 배포 환경 사양을 실시간으로 종합 진단합니다.
"""

import time
import os
import platform
from datetime import datetime
from fastapi import APIRouter
from typing import Dict, Any

from data.data_manager import get_connection
from logic.price_fetcher import get_exchange_rate_usd_krw, get_kr_stock_price, get_us_stock_price
from backend.services import market_service

router = APIRouter(prefix="/api/system", tags=["System Diagnostics"])

@router.get("/benchmark")
def run_system_benchmark() -> Dict[str, Any]:
    """
    서버 및 외부 API 통신 지연시간 실시간 측정 및 벤치마크 진단 API
    (DB 연결, 환율 수집, 국내/해외 주식 시세 API 응답속도 측정)
    """
    total_start = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. DB (Supabase PostgreSQL) Ping Latency
    db_ms = None
    db_status = "오류"
    try:
        t0 = time.time()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        db_ms = round((time.time() - t0) * 1000, 1)
        db_status = "정상"
    except Exception as e:
        db_status = f"실패: {e}"

    # 2. USD/KRW 실시간 환율 수집 속도
    rate_ms = None
    rate_val = None
    rate_src = "미상"
    try:
        t0 = time.time()
        rate_val, rate_src = get_exchange_rate_usd_krw()
        rate_ms = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        rate_src = f"실패: {e}"

    # 3. 국내 주식 시세 샘플 (삼성전자 005930) 수집 속도
    kr_ms = None
    kr_val = None
    kr_src = "미상"
    try:
        t0 = time.time()
        kr_val, kr_src = get_kr_stock_price("005930")
        kr_ms = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        kr_src = f"실패: {e}"

    # 4. 미국 주식 시세 샘플 (Vanguard VT) 수집 속도
    us_ms = None
    us_val = None
    us_src = "미상"
    try:
        t0 = time.time()
        us_val, us_src = get_us_stock_price("VT", usd_krw=rate_val or 1380.0)
        us_ms = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        us_src = f"실패: {e}"

    # 5. 인메모리 캐시 상태
    now = time.time()
    last_fetch = market_service.last_price_fetch_time
    cache_age_sec = round(now - last_fetch, 1) if last_fetch > 0 else None
    cache_alive = bool(market_service.price_data and cache_age_sec is not None and cache_age_sec < market_service.cache_ttl_seconds)

    total_duration_sec = round(time.time() - total_start, 2)

    # 배포 환경 식별
    env_name = "Render Production" if os.getenv("RENDER") else ("Docker/Cloud" if os.getenv("KUBERNETES_SERVICE_HOST") else "Local Development")

    return {
        "status": "success",
        "timestamp": now_str,
        "environment": env_name,
        "platform": platform.platform(),
        "total_benchmark_time_sec": total_duration_sec,
        "metrics": {
            "database": {
                "name": "Supabase PostgreSQL",
                "latency_ms": db_ms,
                "status": db_status
            },
            "exchange_rate": {
                "name": "USD/KRW 환율",
                "rate": rate_val,
                "latency_ms": rate_ms,
                "source": rate_src
            },
            "kr_stock_sample": {
                "ticker": "005930 (삼성전자)",
                "price": kr_val,
                "latency_ms": kr_ms,
                "source": kr_src
            },
            "us_stock_sample": {
                "ticker": "VT (Vanguard Total World Stock)",
                "price_krw": us_val,
                "latency_ms": us_ms,
                "source": us_src
            },
            "memory_cache": {
                "is_active": cache_alive,
                "age_seconds": cache_age_sec,
                "ttl_seconds": market_service.cache_ttl_seconds,
                "cached_items_count": len(market_service.price_data) if market_service.price_data else 0
            }
        }
    }
