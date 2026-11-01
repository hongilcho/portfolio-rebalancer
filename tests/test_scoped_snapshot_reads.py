from data import data_manager
from backend.routers import dashboard


def test_facade_forwards_scope_without_changing_default_overview(mocker):
    ctx=object();mocker.patch.object(data_manager,'_context',return_value=ctx)
    read=mocker.patch.object(data_manager.snapshots,'get_overview_batch_data',return_value={})
    data_manager.get_overview_batch_data('p')
    read.assert_called_with(ctx,portfolio_id='p')
    data_manager.get_overview_batch_data()
    read.assert_called_with(ctx,portfolio_id=None)


def test_bundle_requests_only_the_selected_financial_book(mocker):
    reader=mocker.patch.object(dashboard,'get_overview_batch_data',return_value={})
    mocker.patch.object(dashboard,'prepare_dividend_cache')
    mocker.patch.object(dashboard,'begin_dividend_request')
    mocker.patch.object(dashboard,'get_dividend_status',return_value={})
    mocker.patch.object(dashboard.market_service,'get_prices',return_value=([],{}))
    mocker.patch.object(dashboard.market_service,'request_snapshot',return_value={'usd_krw':1400,'rate_source':'fixed'})
    mocker.patch.object(dashboard.market_service,'request_status',return_value={})
    dashboard.get_dashboard_bundle('synthetic-p')
    reader.assert_called_once_with(portfolio_id='synthetic-p')
