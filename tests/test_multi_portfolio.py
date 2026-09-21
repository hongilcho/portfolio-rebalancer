import pytest
from data.data_manager import (
    init_db, get_portfolios, get_portfolio, create_portfolio, update_portfolio, delete_portfolio,
    get_all_accounts, add_account, get_all_assets, add_asset, delete_account, delete_asset
)
from backend.routers.portfolios import get_all_portfolios_overview

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_portfolio_crud():
    # 1. Check default portfolio exists
    portfolios = get_portfolios()
    assert len(portfolios) >= 1
    default_p = next((p for p in portfolios if p["id"] == "default"), None)
    assert default_p is not None
    assert default_p["is_default"] is True

    # 2. Create a test portfolio
    success, msg, new_p = create_portfolio("테스트 포트폴리오 B", "테스트용 설명 메모")
    assert success is True
    assert new_p is not None
    p_id = new_p["id"]
    assert new_p["name"] == "테스트 포트폴리오 B"
    assert new_p["description"] == "테스트용 설명 메모"

    # 3. Retrieve and Update
    fetched = get_portfolio(p_id)
    assert fetched["id"] == p_id

    success, msg = update_portfolio(p_id, "수정된 포트폴리오 B", "수정된 메모")
    assert success is True
    updated = get_portfolio(p_id)
    assert updated["name"] == "수정된 포트폴리오 B"
    assert updated["description"] == "수정된 메모"

    # 4. Delete protection
    # Cannot delete default
    success, msg = delete_portfolio("default")
    assert success is False

    # Can delete newly created empty portfolio
    success, msg = delete_portfolio(p_id)
    assert success is True
    assert get_portfolio(p_id) is None

def test_multi_portfolio_isolation():
    # 1. Create Portfolio 2
    success, msg, p2 = create_portfolio("격리 테스트 포트폴리오 2", "격리성 검증")
    assert success is True
    p2_id = p2["id"]

    try:
        # 2. Add an account to Portfolio 2
        acc_no = f"test_acc_{p2_id[:6]}"
        success, msg = add_account(
            account_no=acc_no,
            account_alias="테스트2번계좌",
            account_type="위탁",
            deposit_krw=100000.0,
            portfolio_id=p2_id
        )
        assert success is True

        # 3. Add asset to Portfolio 2 with same ticker as might exist in default
        success, msg = add_asset(
            name="격리테스트 ETF",
            ticker="999990",
            market="KR",
            target_weight=40.0,
            portfolio_id=p2_id
        )
        assert success is True

        # 4. Verify isolation
        p2_accounts = get_all_accounts(portfolio_id=p2_id)
        default_accounts = get_all_accounts(portfolio_id="default")

        assert any(a["account_no"] == acc_no for a in p2_accounts)
        assert not any(a["account_no"] == acc_no for a in default_accounts)

        p2_assets = get_all_assets(portfolio_id=p2_id)
        default_assets = get_all_assets(portfolio_id="default")

        assert any(a["ticker"] == "999990" for a in p2_assets)
        assert not any(a["ticker"] == "999990" for a in default_assets)

    finally:
        # Clean up created account and asset before deleting portfolio
        for a in get_all_accounts(portfolio_id=p2_id):
            delete_account(a["id"])
        for ast in get_all_assets(portfolio_id=p2_id):
            delete_asset(ast["id"])
        delete_portfolio(p2_id)

def test_all_portfolios_overview():
    # Test overview summary endpoint logic
    ov_crypto = get_all_portfolios_overview(include_crypto=True)
    assert "grand_total" in ov_crypto
    assert "portfolios" in ov_crypto
    assert "crypto" in ov_crypto
    assert "aggregated_assets" in ov_crypto

    gt_crypto = ov_crypto["grand_total"]
    assert gt_crypto["total_eval"] > 0
    assert gt_crypto["total_buy"] > 0

    ov_no_crypto = get_all_portfolios_overview(include_crypto=False)
    gt_no_crypto = ov_no_crypto["grand_total"]
    assert gt_no_crypto["crypto_total_eval"] == 0.0
    assert gt_no_crypto["total_eval"] <= gt_crypto["total_eval"]
