import pytest

@pytest.fixture
def mock_accounts():
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
