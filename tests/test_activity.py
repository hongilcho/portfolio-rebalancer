"""Read-only activity API validation must reject bad pages/dates before DB access."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.routers.activity import router
from data.repositories.activity import read_page
from datetime import date
import pytest
from types import SimpleNamespace

@pytest.mark.parametrize('query',[
 'start_date=no&end_date=2026-10-08',
 'start_date=2026-10-01&end_date=2026-10-08&page=0',
 'start_date=2026-10-01&end_date=2026-10-08&page_size=101',
 'start_date=2026-10-01&end_date=2026-10-08&category=UNKNOWN'])
def test_invalid_query_never_connects(query,mocker):
    connect=mocker.patch('data.data_manager.get_connection',side_effect=AssertionError('must not connect'))
    app=FastAPI();app.include_router(router)
    assert TestClient(app).get('/api/activity/p?'+query).status_code==422
    connect.assert_not_called()

def test_inverted_dates_rejected_before_connect():
    ctx=SimpleNamespace(connect=lambda:pytest.fail('must not connect'))
    with pytest.raises(ValueError,match='시작일'):read_page(ctx,'p',date(2026,10,8),date(2026,10,1))
