"""
pytest 공통 테스트 픽스처(Fixtures) 모듈
========================================
리밸런싱 계산 및 API 테스트를 위한 모의(Mock) 계좌, 자산, 보유종목 픽스처를 제공합니다.
"""

import socket
import threading
import pytest
import psycopg2
import requests
from curl_cffi import requests as curl_requests

# Apply before importing any application module during collection. Never read
# local credentials, open a real PostgreSQL connection, or contact market APIs.
_isolation = pytest.MonkeyPatch()
for key, value in {
    "PORTFOLIO_LOAD_CONFIG_FILES": "0",
    "PERFORMANCE_CLOSE_SCHEDULER_ENABLED": "0",
    "SUPABASE_URL": "",
    "APP_PASSWORD": "test-only",
    "NAMUH_APP_KEY": "",
    "NAMUH_APP_SECRET": "",
}.items():
    _isolation.setenv(key, value)


def _blocked_io(*args, **kwargs):
    raise RuntimeError("Tests cannot access a real database or network; use fixtures.")

_socketpair_context = threading.local()
_original_connect = socket.socket.connect
_original_socketpair = socket.socketpair


def _guarded_connect(sock, address):
    # Windows asyncio builds its internal self-pipe with socketpair's fallback.
    # Only that thread-local construction may connect, never application IO.
    if getattr(_socketpair_context, 'active', False):
        return _original_connect(sock, address)
    return _blocked_io()


def _internal_socketpair(*args, **kwargs):
    _socketpair_context.active = True
    try:
        return _original_socketpair(*args, **kwargs)
    finally:
        _socketpair_context.active = False


_isolation.setattr(psycopg2, "connect", _blocked_io)
_isolation.setattr(socket.socket, "connect", _guarded_connect)
_isolation.setattr(socket, "socketpair", _internal_socketpair)
_isolation.setattr(socket.socket, "connect_ex", _blocked_io)
_isolation.setattr(socket, "create_connection", _blocked_io)
_isolation.setattr(requests.sessions.Session, "request", _blocked_io)
_isolation.setattr(curl_requests.Session, "request", _blocked_io)


def pytest_collection_modifyitems(items):
    for item in items:
        if (item.path.name in {"test_multi_portfolio.py", "test_fx_weighted_average.py"}
                or item.name == "test_deposit_asset_auto_creates_account_and_holdings"):
            item.add_marker(pytest.mark.skip(
                reason="Legacy tests require a separate isolated PostgreSQL environment."
            ))


def pytest_unconfigure(config):
    _isolation.undo()

@pytest.fixture
def mock_accounts():
    """모의 계좌 목록 (일반계좌, 연금계좌) 픽스처"""
    return [
        {
            "id": "acc_1",
            "account_no": "111",
            "account_alias": "일반계좌",
            "account_type": "종합매매",
            "deposit_krw": 1000000,
            "deposit_usd": 1000,
            "annual_limit": 0,
            "tax_limit": 0,
            "priority": 1
        },
        {
            "id": "acc_2",
            "account_no": "222",
            "account_alias": "연금계좌",
            "account_type": "연금저축계좌",
            "deposit_krw": 5000000,
            "deposit_usd": 0,
            "annual_limit": 15000000,
            "tax_limit": 6000000,
            "priority": 2
        }
    ]

@pytest.fixture
def mock_assets():
    return [
        {
            "id": "ast_1",
            "name": "삼성전자",
            "ticker": "005930",
            "market": "KR",
            "target_weight": 50.0,
            "allowed_accounts": ["acc_1", "acc_2"],
            "is_risk_asset": 1
        },
        {
            "id": "ast_2",
            "name": "TIGER 미국S&P500",
            "ticker": "360750",
            "market": "KR",
            "target_weight": 30.0,
            "allowed_accounts": ["acc_1", "acc_2"],
            "is_risk_asset": 1
        },
        {
            "id": "ast_3",
            "name": "KODEX KOFR금리액티브",
            "ticker": "423160",
            "market": "KR",
            "target_weight": 20.0,
            "allowed_accounts": ["acc_1", "acc_2"],
            "is_risk_asset": 0
        }
    ]

@pytest.fixture
def mock_holdings():
    return [
        {
            "account_id": "acc_1",
            "asset_id": "ast_1",
            "quantity": 10.0,
            "avg_price": 75000.0,
            "currency": "KRW",
            "exchange_rate": 1.0,
            "asset_name": "삼성전자",
            "ticker": "005930",
            "market": "KR",
            "is_risk_asset": 1
        }
    ]

@pytest.fixture
def mock_price_data():
    return [
        {
            "id": "ast_1",
            "price_krw": 80000.0,
            "price_usd": 60.0
        },
        {
            "id": "ast_2",
            "price_krw": 15000.0,
            "price_usd": 11.0
        },
        {
            "id": "ast_3",
            "price_krw": 105000.0,
            "price_usd": 80.0
        }
    ]
