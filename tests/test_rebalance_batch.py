"""Bulk reads must preserve the pre-refactor orders and financial summaries."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.routers import rebalance


def sample_batch():
    accounts = [
        dict(id="normal", account_alias="A", account_type="종합매매", priority=2,
             deposit_krw=500000, deposit_usd=300, annual_limit=0, tax_limit=0),
        dict(id="irp", account_alias="B", account_type="IRP", priority=1,
             deposit_krw=300000, deposit_usd=0, annual_limit=18000000,
             tax_limit=9000000, current_year_deposit=0),
        dict(id="cma", account_alias="C", account_type="CMA", priority=3,
             deposit_krw=9000000, deposit_usd=0, annual_limit=0, tax_limit=0),
    ]
    assets = [
        dict(id="kr", name="국내주식", ticker="005930", market="KR",
             target_weight=40, allowed_accounts=["normal", "irp"], is_risk_asset=True),
        dict(id="us", name="미국채", ticker="SGOV", market="US",
             target_weight=30, allowed_accounts=["normal"], is_risk_asset=False),
        dict(id="safe", name="국내채권", ticker="bond", market="KR",
             target_weight=20, allowed_accounts=["normal", "irp"], is_risk_asset=False),
        dict(id="deposit", name="예금", ticker="DEP-test", market="KR",
             target_weight=10, allowed_accounts=[], is_risk_asset=False,
             is_deposit=True, deposit_principal=500000, lock_rebalance_sell=True),
        dict(id="inactive", name="비활성 보유종목", ticker="old", market="KR",
             target_weight=0, allowed_accounts=["normal"], is_risk_asset=True,
             is_active=False),
        dict(id="excluded", name="비중 제외", ticker="outside", market="KR",
             target_weight=0, allowed_accounts=["normal"], is_risk_asset=False,
             include_in_rebalance=False),
    ]
    holdings = [
        dict(account_id="normal", asset_id="kr", quantity=30, avg_price=60000),
        dict(account_id="normal", asset_id="us", quantity=5, avg_price=125000,
             avg_price_usd=100, buy_fx_rate=1250),
        dict(account_id="normal", asset_id="inactive", quantity=2, avg_price=8000),
        dict(account_id="normal", asset_id="excluded", quantity=1, avg_price=100000),
        dict(account_id="irp", asset_id="safe", quantity=15, avg_price=9000),
    ]
    return dict(accounts=accounts, assets=assets, holdings=holdings)


PRICE_MAP = dict(kr=80000, us=140000, safe=10000, deposit=510000,
                 inactive=10000, excluded=110000)


@pytest.mark.parametrize("scenario", ["NEW_CASH", "DRIFT", "PERIODIC"])
@pytest.mark.parametrize("new_cash", [0, 200000])
def test_bulk_rebalance_matches_previous_results(monkeypatch, scenario, new_cash):
    batch = sample_batch()
    reader = Mock(return_value=copy.deepcopy(batch))
    monkeypatch.setattr(rebalance, "get_rebalance_batch_data", reader)
    prices = Mock(return_value=([], PRICE_MAP))
    monkeypatch.setattr(rebalance.market_service, "get_prices", prices)
    monkeypatch.setattr(rebalance.market_service, "request_snapshot", lambda: {"usd_krw": 1400})
    result = rebalance.calculate_plan(rebalance.CalculateRebalanceRequest(
        portfolio_id="selected", scenario=scenario, new_cash_krw=new_cash))
    baseline = json.loads((Path(__file__).parent / "fixtures/rebalance_before_batch.json").read_text(encoding="utf-8"))
    assert result == baseline[f"{scenario}_{new_cash}"]
    reader.assert_called_once_with("selected")
    prices.assert_called_once_with(force_refresh=True)


def test_missing_accounts_do_not_request_prices(monkeypatch):
    reader = Mock(return_value=dict(accounts=[], assets=[{"id": "a"}], holdings=[]))
    monkeypatch.setattr(rebalance, "get_rebalance_batch_data", reader)
    prices = Mock()
    monkeypatch.setattr(rebalance.market_service, "get_prices", prices)
    with pytest.raises(HTTPException) as error:
        rebalance.calculate_plan(rebalance.CalculateRebalanceRequest(portfolio_id=None))
    assert error.value.status_code == 400
    reader.assert_called_once_with("default")
    prices.assert_not_called()


def test_market_failure_still_prevents_orders(monkeypatch):
    monkeypatch.setattr(rebalance, "get_rebalance_batch_data", lambda pid: sample_batch())
    monkeypatch.setattr(rebalance.market_service, "get_prices",
                        Mock(side_effect=HTTPException(status_code=503, detail="Unavailable")))
    with pytest.raises(HTTPException) as error:
        rebalance.calculate_plan(rebalance.CalculateRebalanceRequest())
    assert error.value.status_code == 503
