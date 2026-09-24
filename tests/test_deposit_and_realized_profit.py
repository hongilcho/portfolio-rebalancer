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

def test_deposit_asset_auto_creates_account_and_holdings():
    from data.data_manager import add_asset, get_all_assets, get_all_accounts, get_holdings_by_account, delete_asset, create_portfolio, delete_portfolio

    # 0. 테스트용 독립 포트폴리오 생성
    p_ok, _, port = create_portfolio("테스트 예금 포트폴리오")
    assert p_ok and port
    test_pid = port['id']

    acc_no = f"123-999-{test_pid[:4]}"
    principal = 5000000.0

    try:
        # 1. 예금 자산 추가 (순수 자산으로 등록)
        ok, msg = add_asset(
            name="테스트 카카오뱅크 예금",
            ticker="",
            market="KR",
            target_weight=10.0,
            portfolio_id=test_pid,
            is_deposit=True,
            deposit_principal=principal,
            interest_rate=3.8,
            start_date="2026-01-01",
            maturity_date="2027-01-01",
            account_no=acc_no
        )
        assert ok, f"add_asset failed: {msg}"

        # 2. 계좌(accounts) 테이블에 가상 계좌가 생성되지 않았는지 확인 (순수 자산 격리)
        accs = get_all_accounts(portfolio_id=test_pid)
        matching_accs = [a for a in accs if a['account_no'] == acc_no or a.get('account_type') == '정기예금']
        assert len(matching_accs) == 0, "정기예금은 accounts 테이블에 가상 계좌로 생성되면 안 됩니다."

        # 3. 자산 테이블 확인 및 account_no 확인
        assets = get_all_assets(portfolio_id=test_pid)
        matching_assets = [a for a in assets if a['account_no'] == acc_no]
        assert len(matching_assets) == 1
        dep_asset = matching_assets[0]
        assert dep_asset['is_deposit'] is True
        assert dep_asset['deposit_principal'] == principal

        # 4. 대시보드 요약 집계에서 정기예금이 자산으로 정상 합산되는지 확인
        from backend.routers.dashboard import get_dashboard_summary
        dash = get_dashboard_summary(portfolio_id=test_pid)
        dep_stock_items = [item for item in dash['stock_assets'] if item['asset_id'] == dep_asset['id']]
        assert len(dep_stock_items) == 1
        assert dep_stock_items[0]['is_deposit'] is True
        assert dep_stock_items[0]['eval_amount'] >= principal
        assert dep_stock_items[0]['buy_amount'] == principal
        # 대시보드 계좌 목록에 가상 계좌가 없음을 재확인
        assert len([a for a in dash['accounts'] if a.get('account_type') == '정기예금']) == 0

        # 5. 자산 삭제 확인
        del_ok, _ = delete_asset(dep_asset['id'])
        assert del_ok
        assets_after = get_all_assets(portfolio_id=test_pid)
        assert len([a for a in assets_after if a['account_no'] == acc_no]) == 0
    finally:
        delete_portfolio(test_pid)
