"""Restore and verify ONLY a loopback PostgreSQL database, never production.

Input: backups/local_validation/local_connection.json and a pg_dump archive.
Output: metadata-only report; restored financial records stay in ignored backups/.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOCAL = ROOT / "backups/local_validation"
TABLES = ("portfolios", "accounts", "assets", "holdings", "trade_history", "crypto_holdings", "market_cache")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve()
    if ROOT / "backups" not in archive.parents:
        raise ValueError("Archive must be under ignored backups/")
    metadata = json.loads(archive.with_name("metadata.json").read_text())
    with archive.open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == metadata["archive_sha256"])
    settings = json.loads((LOCAL / "local_connection.json").read_text())
    if settings.get("host") != "127.0.0.1" or settings.get("port") != 55437 or settings.get("dbname") != "postgres":
        raise ValueError("Only the dedicated local verification server is allowed")
    name = "portfolio_verify_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    admin = psycopg2.connect(**settings)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    admin.close()
    settings["dbname"] = name
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("PG"):
            del env[key]
    env.update(PGHOST="127.0.0.1", PGPORT="55437", PGUSER=settings["user"],
               PGPASSWORD=settings["password"], PGDATABASE=name)
    with (LOCAL / "restore.log").open("wb") as log:
        subprocess.run([str(LOCAL / "pgsql/bin/pg_restore.exe"), "--no-password", "--no-owner", "--no-privileges", "--schema=public", "--exit-on-error", "--dbname=" + name, str(archive)], env=env, stdout=log, stderr=log, check=True)
    report = {"local_database": name, "restored_scope": "public app schema; Supabase system schemas/roles are not restored", "checks": []}

    def check(label, function):
        function()
        report["checks"].append(label)
        print("PASS:", label)

    os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES="0", SUPABASE_URL=make_dsn(**settings),
                      APP_PASSWORD="local-verification-only", NAMUH_APP_KEY="", NAMUH_APP_SECRET="")
    from data import data_manager as dm

    def query(statement, params=()):
        with psycopg2.connect(**settings) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(statement, params)
                return [dict(row) for row in cursor.fetchall()] if cursor.description else []

    counts = {t: query("SELECT count(*) AS n FROM " + t)[0]["n"] for t in TABLES}
    check("backup restores all seven app tables and expected row counts", lambda: require(counts == metadata["tables"]))
    report["restored_counts"] = counts
    original_columns = {t: metadata["columns"][t] for t in TABLES}

    def hashes():
        output = {}
        for table in TABLES:
            columns = original_columns[table]
            statement = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
                sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(table),
                sql.Identifier("key" if table == "market_cache" else "id"))
            output[table] = hashlib.sha256(json.dumps(query(statement), sort_keys=True, default=str).encode()).hexdigest()
        return output

    before = hashes()
    check("schema upgrade succeeds on restored production schema", dm.init_db)
    check("schema upgrade preserves every original app row and value", lambda: require(hashes() == before))
    check("schema upgrade can run twice without changing original data", lambda: (dm.init_db(), require(hashes() == before)))
    check("legacy settlements remain NULL and sequences are unique", lambda: require(query("SELECT count(*) AS n FROM trade_history WHERE cash_delta_krw IS NOT NULL OR cash_delta_usd IS NOT NULL")[0]["n"] == 0 and query("SELECT count(DISTINCT trade_sequence) AS n FROM trade_history")[0]["n"] == counts["trade_history"]))
    barrier = threading.Barrier(2)

    def initialize(_):
        barrier.wait(timeout=10)
        dm.init_db()

    def concurrent_init():
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(initialize, range(2)))
        require(hashes() == before)

    check("two simultaneous initializers complete without lost data", concurrent_init)

    def legacy_guard():
        old = query("SELECT id FROM trade_history WHERE trade_type IN ('BUY','SELL') LIMIT 1")
        if old:
            require(not dm.delete_trade(old[0]["id"])[0])
            require(hashes() == before)

    check("legacy trade deletion is rejected without any data changes", legacy_guard)
    # Isolate synthetic trade cases in new accounts, leaving restored accounts alone.
    query("INSERT INTO accounts (id,account_no,account_alias,account_type,deposit_krw,deposit_usd,portfolio_id) VALUES ('verify_acc','VERIFY-LOCAL','Local verification','GENERAL',10000000,5000,'default')")
    query("INSERT INTO assets (id,name,ticker,market,portfolio_id) VALUES ('verify_us','Verification US','VERIFY_US','US','default'),('verify_kr','Verification KR','VERIFY_KR','KR','default')")

    def trade(kind, qty=10, price=100, asset="verify_us", currency="USD", fx=1300):
        result = dm.execute_trade("2026-10-04", "verify_acc", asset, kind, qty, price, currency, fx)
        require(result[0])
        return query("SELECT id FROM trade_history WHERE account_id='verify_acc' ORDER BY trade_sequence DESC LIMIT 1")[0]["id"]

    def balance():
        return query("SELECT deposit_krw,deposit_usd FROM accounts WHERE id='verify_acc'")[0]

    def state():
        return {t: query("SELECT * FROM " + t + " WHERE " + ("id='verify_acc'" if t == "accounts" else "account_id='verify_acc'") + " ORDER BY id") for t in ("accounts", "holdings", "trade_history")}

    def usd_roundtrip():
        start = balance()
        first = trade("BUY")
        second = trade("BUY", price=150, fx=1400)
        sold = trade("SELL", qty=5, price=160, fx=1370)
        h = query("SELECT * FROM holdings WHERE account_id='verify_acc' AND asset_id='verify_us'")[0]
        require((h["quantity"], h["avg_price_usd"], h["buy_fx_rate"], h["avg_price"]) == (15,125,1360,170000))
        require(dm.delete_trades([second, sold, first])[0])
        require(balance() == start)
        require(query("SELECT quantity FROM holdings WHERE account_id='verify_acc' AND asset_id='verify_us'")[0]["quantity"] == 0)

    check("real PostgreSQL USD weighted cost and batch reversal restore cash", usd_roundtrip)

    def oversell_rollback():
        bought = trade("BUY", qty=10, price=100, asset="verify_kr", currency="KRW", fx=1)
        sold = trade("SELL", qty=5, price=110, asset="verify_kr", currency="KRW", fx=1)
        start = state()
        require(not dm.delete_trade(bought)[0])
        require(state() == start)
        require(dm.delete_trades([bought,sold])[0])

    check("failed deletion rolls back history, cash and holdings", oversell_rollback)

    def injected_failure():
        bought = trade("BUY", qty=10, price=100, asset="verify_kr", currency="KRW", fx=1)
        sold = trade("SELL", qty=5, price=110, asset="verify_kr", currency="KRW", fx=1)
        start = state()
        query("CREATE FUNCTION public.verify_write_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected local write failure'; END $$")
        query("CREATE TRIGGER verify_write_failure BEFORE UPDATE ON holdings FOR EACH ROW EXECUTE FUNCTION public.verify_write_failure()")
        try:
            require(not dm.delete_trades([bought,sold])[0])
            require(state() == start)
        finally:
            query("DROP TRIGGER verify_write_failure ON holdings")
            query("DROP FUNCTION public.verify_write_failure()")
        require(dm.delete_trades([bought,sold])[0])

    check("PostgreSQL trigger error rolls back every batch write", injected_failure)

    def simultaneous_buys():
        query("UPDATE accounts SET deposit_krw=1000 WHERE id='verify_acc'")
        gate = threading.Barrier(2)
        def buy(_):
            gate.wait(timeout=10)
            return dm.execute_trade("2026-10-04","verify_acc","verify_kr","BUY",1,700,"KRW",1)[0]
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(buy, range(2)))
        require(sorted(results) == [False, True])
        require(balance()["deposit_krw"] == 300)
        ids = [r["id"] for r in query("SELECT id FROM trade_history WHERE account_id='verify_acc'")]
        require(dm.delete_trades(ids)[0])
        require(balance()["deposit_krw"] == 1000)

    check("concurrent buys cannot overspend the same cash balance", simultaneous_buys)

    def simultaneous_deletes():
        bought = trade("BUY", qty=1,price=100,asset="verify_kr",currency="KRW",fx=1)
        gate = threading.Barrier(2)
        def remove(_):
            gate.wait(timeout=10)
            return dm.delete_trade(bought)[0]
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(remove,range(2)))
        require(sorted(results) == [False,True])
        require(balance()["deposit_krw"] == 1000)

    check("concurrent deletion reverses cash exactly once", simultaneous_deletes)

    def buy_while_deleting():
        bought = trade("BUY",qty=1,price=100,asset="verify_kr",currency="KRW",fx=1)
        gate = threading.Barrier(2)
        def operation(kind):
            gate.wait(timeout=10)
            if kind == "delete":
                return dm.delete_trade(bought)[0]
            return dm.execute_trade("2026-10-04","verify_acc","verify_kr","BUY",1,200,"KRW",1)[0]
        with ThreadPoolExecutor(max_workers=2) as workers:
            require(all(workers.map(operation,("delete","buy"))))
        require(balance()["deposit_krw"] == 800)
        h = query("SELECT quantity,avg_price FROM holdings WHERE account_id='verify_acc' AND asset_id='verify_kr'")[0]
        require((h["quantity"],h["avg_price"]) == (1,200))

    check("concurrent buy and deletion preserve remaining cash and cost", buy_while_deleting)
    dm.get_connection_pool().closeall()
    report["status"] = "passed"
    report["check_count"] = len(report["checks"])
    report["backup_sha256"] = metadata["archive_sha256"]
    (LOCAL / "verification_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Verification completed:", len(report["checks"]), "checks")


def require(condition):
    if not condition:
        raise AssertionError("Verification condition failed")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Local verification failed:", type(error).__name__)
        raise SystemExit(1)
