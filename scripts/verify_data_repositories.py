"""Compare persistence before/after refactoring using synthetic loopback DBs.

Requires backups/local_validation/local_connection.json and the dedicated PG
server at 127.0.0.1:55437. Never reads production credentials or market data.
The baseline comes from a local Git commit. SQL/parameters, return values,
commit/rollback/close order and every app table are compared after each step.
"""
import argparse
from datetime import datetime
import hashlib
import importlib
import inspect
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import types

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "backups/local_validation"
TABLES = ("portfolios", "accounts", "assets", "holdings", "trade_history",
          "crypto_holdings", "market_cache")
FIXED_TIME = datetime(2026, 10, 5, 12)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_TIME if tz is None else FIXED_TIME.replace(tzinfo=tz)


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class TraceCursor:
    def __init__(self, cursor, trace, lease):
        self.cursor, self.trace, self.lease = cursor, trace, lease

    def execute(self, statement, params=None):
        self.trace.append((self.lease, statement, params))
        # Freeze database-generated timestamps too, for full row comparison.
        statement = statement.replace(
            "CURRENT_TIMESTAMP", "'2026-10-05 12:00:00+00'::timestamptz")
        return self.cursor.execute(statement, params)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class TraceConnection:
    def __init__(self, conn, trace, lease):
        self.conn, self.trace, self.lease = conn, trace, lease

    def cursor(self, **kwargs):
        return TraceCursor(self.conn.cursor(**kwargs), self.trace, self.lease)

    def commit(self):
        self.trace.append((self.lease, "COMMIT"))
        self.conn.commit()

    def rollback(self):
        self.trace.append((self.lease, "ROLLBACK"))
        self.conn.rollback()

    def close(self):
        self.trace.append((self.lease, "CLOSE"))
        self.conn.close()


class Runner:
    def __init__(self, module, settings):
        self.module, self.settings = module, settings
        self.trace, self.steps = [], []
        self.leases = itertools.count(1)
        ids = itertools.count(1)
        module.get_connection = self.connect
        module.generate_id = lambda: f"qa_{next(ids):04d}"
        module.clear_all_caches = lambda: self.trace.append(("invalidate",))

    def connect(self):
        lease = next(self.leases)
        self.trace.append((lease, "OPEN"))
        return TraceConnection(psycopg2.connect(**self.settings), self.trace, lease)

    def query(self, statement, params=None):
        with psycopg2.connect(**self.settings) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(statement, params)
                return [dict(row) for row in cursor.fetchall()] if cursor.description else []

    def state(self):
        return {table: self.query(sql.SQL("SELECT * FROM {} ORDER BY {}").format(
            sql.Identifier(table), sql.Identifier("key" if table == "market_cache" else "id")))
            for table in TABLES}

    def call(self, label, method, *args, **kwargs):
        self.trace.clear()
        self.leases = itertools.count(1)
        result = getattr(self.module, method)(*args, **kwargs)
        state = self.state()
        self.steps.append(dict(label=label, result=result, state_hash=digest(state),
                               trace_hash=digest(self.trace),
                               sql_count=sum(len(event) == 3 for event in self.trace),
                               leases=sum(event[1:] == ("OPEN",) for event in self.trace)))
        return result

    def account(self, number):
        return self.query("SELECT id FROM accounts WHERE account_no=%s", (number,))[0]["id"]

    def asset(self, ticker):
        return self.query("SELECT id FROM assets WHERE ticker=%s", (ticker,))[0]["id"]

    def latest_trade(self, account):
        return self.query("SELECT id FROM trade_history WHERE account_id=%s ORDER BY trade_sequence DESC LIMIT 1", (account,))[0]["id"]


def exercise(r):
    c = r.call
    c("schema creation", "init_db")
    c("schema repeat", "init_db")
    c("invalid portfolio", "create_portfolio", " ")
    second = c("new portfolio", "create_portfolio", "합성 보조", "합성 검증 자료")[2]["id"]
    c("rename portfolio", "update_portfolio", second, "합성 보조 2", "합성 설명")
    c("add KR account", "add_account", " QA-KR ", " 합성 KR ", "종합매매", 1000000, 1000)
    c("add US account", "add_account", "QA-US", "합성 US", "ISA", 1000000, 5000, portfolio_id=second)
    c("duplicate account", "add_account", "QA-KR", "중복", "ISA")
    kr, us = r.account("QA-KR"), r.account("QA-US")
    c("account update", "update_account", kr, "QA-KR", "합성 KR 수정", "종합매매", 1500000, 1000, 0, 0, notes="합성 메모", priority=3)
    c("account limits", "update_account_settings", us, 2, "ANNUAL", 300000)
    c("account exhausted", "update_account_limit_exhausted", us, True)
    c("account priorities", "update_account_priorities", {kr: 1, us: 2})
    c("add KR asset", "add_asset", "합성 KR ETF", "KR_TEST", "KR", 40, [kr, " "+kr+" "])
    c("add US asset", "add_asset", "합성 US ETF", "US_TEST", "US", 60, [us], portfolio_id=second)
    c("duplicate ticker", "add_asset", "중복", "KR_TEST", "KR", 1)
    c("deposit asset", "add_asset", "합성 예금", "DEP_TEST", "US", 10,
      is_deposit=True, deposit_principal=10000000, interest_rate=4,
      start_date="2026-01-01", maturity_date="2027-01-01", account_no="QA-BANK",
      account_id=kr, include_in_rebalance=False, tax_rate=0)
    ka, ua, dep = r.asset("KR_TEST"), r.asset("US_TEST"), r.asset("DEP_TEST")
    c("update asset", "update_asset", ka, "합성 KR ETF 수정", "KR_TEST", "KR", 50, [kr], notes="합성 메모")
    c("archive deposit", "toggle_asset_active", dep, False)
    c("restore deposit", "toggle_asset_active", dep, True)
    c("save KR holdings", "save_account_holdings", kr, [dict(asset_id=ka, quantity=2.5,
      avg_price=100, first_buy_date="2026-01-01", manual_dividend_override=12.5)])
    c("save US holdings", "save_account_holdings", us, [dict(asset_id=ua, quantity=1.25,
      avg_price_usd=100, buy_fx_rate=1400, original_avg_price_usd=95)])
    c("negative manual balance", "save_account_holdings", kr, [dict(asset_id=ka, quantity=-1)])
    c("KR buy", "execute_trade", "2026-10-05", kr, ka, "BUY", 3, 120, "KRW", 1)
    buy = r.latest_trade(kr)
    c("KR sell", "execute_trade", "2026-10-05", kr, ka, "SELL", 1, 140, "KRW", 1)
    sell = r.latest_trade(kr)
    c("USD buy missing rate", "execute_trade", "2026-10-05", us, ua, "BUY", .75, 110, "USD")
    r.query("UPDATE accounts SET deposit_usd=5 WHERE id=%s", (us,))
    c("USD buy mixed settlement", "execute_trade", "2026-10-05", us, ua, "BUY", 1, 100, "USD", 1400)
    mixed = r.latest_trade(us)
    c("undo mixed settlement", "delete_trade", mixed)
    c("repeat undo rejected", "delete_trade", mixed)
    c("oversell rollback", "execute_trade", "2026-10-05", kr, ka, "SELL", 999, 10, "KRW", 1)
    c("insufficient cash rollback", "execute_trade", "2026-10-05", us, ua, "BUY", 99999, 100, "USD", 1400)
    c("invalid trade", "execute_trade", "2026-10-05", kr, ka, "BUY", 0, 100)
    c("batch undo", "delete_trades", [sell, buy])
    c("duplicate undo IDs", "delete_trades", [buy, buy])
    r.query("INSERT INTO trade_history(id,trade_date,account_id,asset_id,trade_type,quantity,price) VALUES ('legacy','2026-01-01',%s,%s,'BUY',1,100)", (kr, ka))
    c("legacy undo rejected", "delete_trade", "legacy")
    c("transfer", "apply_transfer_plan", [dict(account_id=kr, type="DEPOSIT", amount=500),
      dict(account_id=us, type="WITHDRAW", amount=200), dict(account_id="absent", type="DEPOSIT", amount=1)])
    c("transfer rollback", "apply_transfer_plan", [dict(account_id=kr, type="DEPOSIT", amount=500),
      dict(account_id=us, type="WITHDRAW", amount="invalid")])
    c("empty transfer", "apply_transfer_plan", [])
    c("crypto save", "save_crypto_holding", " btc ", .125, 1000000, " 홍일 ", "합성 메모")
    c("crypto negative clamp", "save_crypto_holding", "ETH", -1, -5, "윤아")
    c("cache save", "save_market_cache", "div_US_US_TEST", [dict(date="2026-09-01", amount=.5)])
    c("cache hit", "get_market_cache", "div_US_US_TEST")
    c("cache miss", "get_market_cache", "absent")
    c("portfolios read", "get_portfolios")
    c("portfolio read", "get_portfolio", second)
    c("portfolio missing", "get_portfolio", "absent")
    for method in ("get_all_accounts", "get_all_assets", "get_all_holdings", "get_trade_history"):
        c(method+" all", method)
        c(method+" scoped", method, second)
    c("holdings per account", "get_holdings_by_account", us)
    c("rebalance snapshot", "get_rebalance_batch_data", second)
    c("rebalance empty", "get_rebalance_batch_data", "absent")
    c("overview snapshot", "get_overview_batch_data")
    c("crypto all", "get_crypto_holdings")
    c("crypto owner", "get_crypto_holdings", "홍일")
    payload = dict(deposit_krw=900000, deposit_usd=20, holdings=[dict(ticker="US_TEST",
      quantity=2.25, avg_price=140000, avg_price_usd=100, buy_fx_rate=1400)])
    c("broker sync", "sync_account_with_api", us, payload)
    c("repeat broker sync", "sync_account_with_api", us, payload)
    c("broker clears missing balances", "sync_account_with_api", us, dict(deposit_krw=800000, holdings=[]))
    c("empty broker data", "sync_account_with_api", us, {})
    c("occupied portfolio deletion", "delete_portfolio", second)
    c("account deletion FK rollback", "delete_account", kr)
    c("delete KR asset and trades", "delete_asset", ka)
    c("delete KR account", "delete_account", kr)
    c("delete US asset and trades", "delete_asset", ua)
    c("delete US account", "delete_account", us)
    c("delete empty portfolio", "delete_portfolio", second)
    c("default portfolio protected", "delete_portfolio", "default")
    c("delete deposit", "delete_asset", dep)


def signature(func):
    def annotation(a):
        return a.__name__ if isinstance(a, type) else str(a)
    s = inspect.signature(func)
    return ([(p.name, str(p.kind), repr(p.default), annotation(p.annotation))
             for p in s.parameters.values()], annotation(s.return_annotation))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="410070d")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{7,40}", args.baseline_ref):
        raise ValueError("Use a local hexadecimal commit SHA")
    settings = json.loads((LOCAL / "local_connection.json").read_text())
    if (settings.get("host"), settings.get("port"), settings.get("dbname")) != ("127.0.0.1", 55437, "postgres"):
        raise ValueError("Only the dedicated loopback PostgreSQL is allowed")
    real_connect = psycopg2.connect
    def guarded_connect(dsn=None, *a, **kw):
        parsed = parse_dsn(dsn) if dsn else {}
        parsed.update(kw)
        if parsed.get("host") != "127.0.0.1" or str(parsed.get("port")) != "55437":
            raise RuntimeError("Persistence verification cannot connect to production")
        return real_connect(dsn, *a, **kw)
    psycopg2.connect = guarded_connect
    os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES="0", SUPABASE_URL=make_dsn(**settings),
                      NAMUH_APP_KEY="", NAMUH_APP_SECRET="", APP_PASSWORD="test-only")
    sys.path.insert(0, str(ROOT))
    def blocked(*a, **kw):
        raise RuntimeError("Persistence verification cannot call market providers")
    import requests
    from curl_cffi import requests as curl_requests
    requests.sessions.Session.request = blocked
    curl_requests.Session.request = blocked
    source = subprocess.check_output(["git", "show", args.baseline_ref+":data/data_manager.py"], cwd=ROOT).decode("utf-8")
    before = types.ModuleType("baseline_data_manager")
    exec(compile(source, "baseline_data_manager.py", "exec"), before.__dict__)
    from data import data_manager as after
    for name, func in vars(before).items():
        if inspect.isfunction(func) and func.__module__ == before.__name__:
            assert signature(func) == signature(getattr(after, name)), name+" signature changed"
    assert before.ACCOUNT_TYPES == after.ACCOUNT_TYPES
    assert before.ACCOUNT_TYPE_ALIASES == after.ACCOUNT_TYPE_ALIASES
    for module in (before, importlib.import_module("data.schema"),
                   importlib.import_module("data.repositories.holdings"),
                   importlib.import_module("data.repositories.crypto")):
        module.datetime = FixedDatetime
    from backend.services import market_service
    market_service.usd_krw = 1450
    runners = []
    admin = psycopg2.connect(**settings)
    try:
        admin.autocommit = True
        with admin.cursor() as cursor:
            for tag, module in (("before", before), ("after", after)):
                name = "repo_"+tag+"_"+datetime.now().strftime("%Y%m%d_%H%M%S")
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                runners.append(Runner(module, {**settings, "dbname": name}))
    finally:
        admin.close()
    for runner in runners:
        exercise(runner)
    left, right = runners
    assert len(left.steps) == len(right.steps)
    for a, b in zip(left.steps, right.steps):
        assert a == b, a["label"]+" differs between baseline and refactored persistence"
        print("PASS:", a["label"])
    report = dict(baseline_commit=args.baseline_ref, scenario_count=len(left.steps),
                  comparison="same signatures, SQL/params, returns, transaction events and all table values",
                  databases=[r.settings["dbname"] for r in runners], scenarios=right.steps)
    (LOCAL / "data_repository_refactor_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("All", len(left.steps), "persistence scenarios match; production IO blocked.")


if __name__ == "__main__":
    main()
