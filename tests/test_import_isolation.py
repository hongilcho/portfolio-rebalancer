"""Collection/import must never connect to production resources."""

import importlib
import socket
import pytest
import psycopg2
import requests
from curl_cffi import requests as curl_requests
from backend.services import MarketStateService
from data import data_manager


def test_market_service_construction_has_no_cache_io(mocker):
    cache_reader = mocker.patch('backend.services.get_market_cache')
    service = MarketStateService()
    assert service.price_data is None
    cache_reader.assert_not_called()


def test_app_import_does_not_initialize_db(mocker):
    initialize = mocker.patch('data.data_manager.init_db')
    importlib.import_module('backend.main')
    initialize.assert_not_called()


def test_schema_failure_prevents_startup_and_returns_connection(mocker):
    connection = mocker.Mock()
    mocker.patch.object(data_manager, 'get_connection', return_value=connection)
    mocker.patch.object(data_manager, '_do_init_db_schema', side_effect=RuntimeError('schema unavailable'))
    with pytest.raises(RuntimeError, match='schema unavailable'):
        data_manager.init_db()
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def test_network_and_database_guards_block_io():
    with pytest.raises(RuntimeError, match='Tests cannot access'):
        psycopg2.connect('dbname=test')
    with pytest.raises(RuntimeError, match='Tests cannot access'):
        requests.get('http://127.0.0.1:1')
    with pytest.raises(RuntimeError, match='Tests cannot access'):
        curl_requests.Session().get('http://127.0.0.1:1')
    with socket.socket() as sock:
        with pytest.raises(RuntimeError, match='Tests cannot access'):
            sock.connect(('127.0.0.1', 1))
