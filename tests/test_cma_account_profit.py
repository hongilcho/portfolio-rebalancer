"""Income presentation must never add cash a second time."""
import copy
import sqlite3
from unittest.mock import Mock

import pytest

from data.repositories.snapshots import _overview_account_source
from logic.portfolio_valuation import calculate_portfolio_summary, index_valuation_inputs


def test_journal_sum_is_scoped_unlimited_and_excludes_reversed_and_unpaid():
    db = sqlite3.connect(':memory:')
    db.executescript('''
        CREATE TABLE accounts(id TEXT,portfolio_id TEXT,account_type TEXT,deposit_krw NUMERIC);
        INSERT INTO accounts VALUES('cma','p','CMA',1040),('other','p','CMA',2000),('stock','p','GENERAL',100);
        ATTACH DATABASE ':memory:' AS portfolio_cma;
        CREATE TABLE portfolio_cma.income(portfolio_id TEXT,account_id TEXT,amount_krw NUMERIC,reversed_at TEXT);
        CREATE TABLE portfolio_cma.openings(portfolio_id TEXT,account_id TEXT,amount_krw NUMERIC,reversed_at TEXT);
        INSERT INTO portfolio_cma.openings VALUES('p','cma',10,NULL),('p','other',100,NULL);
        INSERT INTO portfolio_cma.income VALUES('p','cma',500,'reversed'),('p','other',20,NULL),
            ('elsewhere','cma',900,NULL),('p','stock',400,NULL);
    ''')
    db.executemany('INSERT INTO portfolio_cma.income VALUES(?,?,?,NULL)', [('p','cma',1)]*30)
    catalog = Mock()
    catalog.fetchone.return_value = ('portfolio_cma.income', 'portfolio_cma.openings')
    source = _overview_account_source(catalog)
    for _ in range(2):
        rows = {r[0]:r for r in db.execute('SELECT * FROM '+source)}
        assert rows['cma'] == ('cma','p','CMA',1040,40)
        assert rows['other'][-1] == 120
        assert rows['stock'][-1] == 0
    assert db.execute("SELECT deposit_krw FROM accounts WHERE id='cma'").fetchone()[0] == 1040
    db.execute("UPDATE portfolio_cma.openings SET reversed_at='reversed' WHERE account_id='cma'")
    assert db.execute('SELECT cma_interest_krw FROM '+source+" WHERE id='cma'").fetchone()[0] == 30
    db.close()


def test_optional_schema_is_not_created_and_partial_schema_fails_visibly():
    cursor = Mock()
    cursor.fetchone.return_value = (None,None)
    assert _overview_account_source(cursor) == 'accounts'
    assert cursor.execute.call_count == 1
    cursor.fetchone.return_value = ('portfolio_cma.income', None)
    with pytest.raises(RuntimeError,match='incomplete'):
        _overview_account_source(cursor)


def test_cma_profit_adds_income_once_without_changing_cash_assets_or_stock_rate():
    from test_valuation_refactor import sample_snapshot
    from backend.valuation_service import evaluate_portfolio
    from logic.dividend_calculator import calculate_holding_dividends

    batch, quotes, fx = sample_snapshot()
    accounts = [a for a in batch['accounts'] if a['portfolio_id']=='default']
    accounts[0]['account_type'] = 'CMA'
    inputs = index_valuation_inputs(batch['holdings'],batch['trade_history'],quotes)
    def evaluate():
        return evaluate_portfolio(accounts,batch['assets'],inputs,{q['id']:q['price_krw'] for q in quotes},fx,
            calculate_adjustment=lambda h,a,fx,**kw:calculate_holding_dividends(h,a,fx,dividend_records=[],**kw))
    before = evaluate()
    accounts[0]['cma_interest_krw'] = '40'
    unchanged = copy.deepcopy(accounts)
    after = evaluate()
    assert accounts == unchanged
    assert after['cash_assets'] == before['cash_assets']
    assert after['kpi'] == before['kpi']
    assert after['accounts'][1] == before['accounts'][1]
    account = after['accounts'][0]
    assert account['profit_krw'] == pytest.approx(before['accounts'][0]['profit_krw']+40)
    assert account['total_profit_krw'] == account['profit_krw']
    assert account['profit_pct'] == before['accounts'][0]['profit_pct']
    assert account['total_val'] == before['accounts'][0]['total_val']


def test_cash_only_cma_has_income_profit_and_no_invented_stock_return():
    account=dict(id='a',account_no='qa',account_alias='CMA',account_type='CMA',deposit_krw=1040,deposit_usd=0,cma_interest_krw='40')
    result=calculate_portfolio_summary([account],[],index_valuation_inputs([],[],[]),{},{},1400)
    summary=result['accounts'][0]
    assert summary['total_val']==1040 and summary['profit_krw']==40
    assert summary['cma_interest_krw']==40 and summary['profit_pct']==0
    assert result['cash_assets']['total_cash_krw']==1040
