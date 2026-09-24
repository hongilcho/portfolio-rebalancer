import pytest
from datetime import datetime, timedelta
from logic.price_fetcher import calculate_deposit_price
from logic.rebalance_calculator import calculate_rebalancing_plan, compute_realized_summary

def test_calculate_deposit_price_basic():
    # 1,000만원, 연 4%, 180일 경과, 15.4% 과세
    today = datetime.now().date()
    start = today - timedelta(days=180)
    mat = today + timedelta(days=185) # 총 365일 만기

    asset = {
        'deposit_principal': 10000000.0,
        'interest_rate': 4.0,
        'start_date': str(start),
        'maturity_date': str(mat),
        'tax_rate': 15.4
    }

    price, days, gross, net = calculate_deposit_price(asset)
    assert days == 180
    assert abs(gross - 197260.27) < 0.1
    # 197260.27 * 0.154 = 30378.08 -> floor = 30378
    # net = 197260.27 - 30378 = 166882.27
    assert price == 10166882.0

def test_calculate_deposit_price_past_maturity():
    # 만기일이 이미 지난 경우, 만기일까지의 일수만 적용되어야 함
    today = datetime.now().date()
    start = today - timedelta(days=400)
    mat = today - timedelta(days=35) # 365일간 예금 후 만기 경과

    asset = {
        'deposit_principal': 10000000.0,
        'interest_rate': 4.0,
        'start_date': str(start),
        'maturity_date': str(mat),
        'tax_rate': 15.4
    }

    price, days, gross, net = calculate_deposit_price(asset)
    assert days == 365
    assert abs(gross - 400000.0) < 0.1
    # 400,000 * 0.154 = 61,600
    # net = 338,400
    assert price == 10338400.0

def test_rebalance_sell_realized_profit():
    # DRIFT 시나리오: 자산 1의 비중이 높아 매도가 발생해야 함
    accounts = [
        {
            'id': 'acc_1',
            'account_alias': '일반계좌',
            'account_type': '종합매매',
            'deposit_krw': 0.0,
            'deposit_usd': 0.0,
            'priority': 1
        }
    ]
    assets = [
        {
            'id': 'ast_stock',
            'name': '성장주',
            'ticker': '005930',
            'market': 'KR',
            'target_weight': 20.0, # 목표 비중 20%
            'is_risk_asset': True,
            'allowed_accounts': ['acc_1']
        },
        {
            'id': 'ast_safe',
            'name': '단기채권',
            'ticker': '136340',
            'market': 'KR',
            'target_weight': 80.0, # 목표 비중 80%
            'is_risk_asset': False,
            'allowed_accounts': ['acc_1']
        }
    ]
    # 보유 상황: 성장주 100주 (평단가 50,000원, 현재가 100,000원 -> 평가액 1,000만원, 비중 100%)
    holdings = [
        {
            'account_id': 'acc_1',
            'asset_id': 'ast_stock',
            'quantity': 100.0,
            'avg_price': 50000.0 # 평단가 5만원
        }
    ]
    portfolio_assets = {
        'ast_stock': {
            'qty': 100.0,
            'eval_amt_krw': 10000000.0,
            'buy_amt_krw': 5000000.0
        }
    }
    price_map = {
        'ast_stock': 100000.0, # 현재가 10만원 (100% 상승)
        'ast_safe': 100000.0
    }

    trade_plan, transfer_plan, simulated, success, msg = calculate_rebalancing_plan(
        assets=assets,
        portfolio_assets=portfolio_assets,
        accounts=accounts,
        holdings=holdings,
        price_map=price_map,
        total_krw_cash=0.0,
        usd_krw_rate=1300.0,
        scenario="DRIFT",
        new_cash_krw=0.0,
        drift_threshold=5.0
    )

    assert success is True
    sell_trades = [t for t in trade_plan if t['type'] == 'SELL']
    assert len(sell_trades) > 0
    sell_trade = sell_trades[0]
    
    # 목표 비중 20%이므로 1,000만원 중 200만원(20주) 보유 유지, 80주 매도
    assert sell_trade['qty'] == 80.0
    assert sell_trade['price'] == 100000.0
    assert sell_trade['avg_price'] == 50000.0
    assert sell_trade['total_krw'] == 8000000.0
    assert sell_trade['cost_basis_krw'] == 4000000.0 # 80주 * 50,000원
    assert sell_trade['realized_profit_krw'] == 4000000.0 # 800만 - 400만 = +400만원
    assert sell_trade['realized_profit_pct'] == 100.0 # +100%

    summary = compute_realized_summary(trade_plan)
    assert summary['has_sell'] is True
    assert summary['total_sell_amount'] == 8000000.0
    assert summary['total_cost_basis'] == 4000000.0
    assert summary['total_realized_profit'] == 4000000.0
    assert summary['total_realized_return_pct'] == 100.0

def test_locked_deposit_not_sold_in_rebalance():
    # 예금이 목표 비중을 초과하더라도 lock_rebalance_sell=True 이면 매도되지 않아야 함
    accounts = [
        {
            'id': 'acc_1',
            'account_alias': '예금계좌',
            'account_type': '종합매매',
            'deposit_krw': 0.0,
            'deposit_usd': 0.0,
            'priority': 1
        }
    ]
    assets = [
        {
            'id': 'ast_deposit',
            'name': '정기예금',
            'ticker': 'DEP-123456',
            'market': 'KR',
            'target_weight': 30.0, # 목표 비중은 30%
            'is_risk_asset': False,
            'allowed_accounts': ['acc_1'],
            'is_deposit': True,
            'lock_rebalance_sell': True # 리밸런싱 매도 방지 락
        },
        {
            'id': 'ast_stock',
            'name': '주식',
            'ticker': '005930',
            'market': 'KR',
            'target_weight': 70.0,
            'is_risk_asset': True,
            'allowed_accounts': ['acc_1'],
            'is_deposit': False
        }
    ]
    # 보유 상황: 예금 1계약 (원금 1000만원, 현재가 1000만원, 비중 100%)
    holdings = [
        {
            'account_id': 'acc_1',
            'asset_id': 'ast_deposit',
            'quantity': 1.0,
            'avg_price': 10000000.0
        }
    ]
    portfolio_assets = {
        'ast_deposit': {
            'qty': 1.0,
            'eval_amt_krw': 10000000.0,
            'buy_amt_krw': 10000000.0
        }
    }
    price_map = {
        'ast_deposit': 10000000.0,
        'ast_stock': 50000.0
    }

    trade_plan, transfer_plan, simulated, success, msg = calculate_rebalancing_plan(
        assets=assets,
        portfolio_assets=portfolio_assets,
        accounts=accounts,
        holdings=holdings,
        price_map=price_map,
        total_krw_cash=0.0,
        usd_krw_rate=1300.0,
        scenario="DRIFT",
        new_cash_krw=0.0,
        drift_threshold=5.0
    )

    # 예금은 lock_rebalance_sell=True 이므로 매도 주문이 절대 발생하지 않아야 함
    sell_trades = [t for t in trade_plan if t['type'] == 'SELL' and t['asset_id'] == 'ast_deposit']
    assert len(sell_trades) == 0
