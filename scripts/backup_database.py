"""Read-only PostgreSQL logical backup; credentials never enter command arguments.

Requires PostgreSQL 17 pg_dump. Backups and metadata stay under ignored backups/.
Run explicitly, never as part of server startup or pytest.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

import psycopg2
from psycopg2.extensions import parse_dsn
import toml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HOST = "aws-1-ap-northeast-2.pooler.supabase.com"


def connection_settings():
    values = {}
    secrets = ROOT / ".streamlit/secrets.toml"
    if secrets.exists():
        values.update(toml.load(secrets))
    env_file = ROOT / ".env"
    if env_file.exists():
        from dotenv import dotenv_values
        values.update({k: v for k, v in dotenv_values(env_file).items() if v})
    values.update({k: os.environ[k] for k in ("SUPABASE_SESSION_URL", "SUPABASE_URL") if os.environ.get(k)})
    url = values.get("SUPABASE_SESSION_URL") or values.get("SUPABASE_URL")
    if not url:
        raise ValueError("No database connection configured")
    settings = parse_dsn(url)
    if settings.get("host") != EXPECTED_HOST:
        raise ValueError("Unexpected database host; verify configuration first")
    # Same reported Supavisor endpoint, session port; do not persist credentials.
    settings.update(port="5432", sslmode="require", connect_timeout="15",
                    options="-c default_transaction_read_only=on -c statement_timeout=60000")
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, required=True)
    args = parser.parse_args()
    pg_dump = args.pg_bin.resolve() / "pg_dump.exe"
    version = subprocess.check_output([str(pg_dump), "--version"], text=True).strip()
    if " 17." not in version:
        raise ValueError("PostgreSQL 17 pg_dump required")
    settings = connection_settings()
    destination = ROOT / "backups" / datetime.now(timezone.utc).strftime("predeploy_%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True, exist_ok=False)
    metadata = {"backup_tool": version, "read_only": True, "tables": {}, "columns": {}}
    with psycopg2.connect(**settings) as conn:
        # Supavisor can ignore startup options; issue an explicit READ ONLY
        # transaction instead of relying on connection-string options.
        conn.set_session(readonly=True)
        with conn.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            assert cursor.fetchone()[0] == "on"
            cursor.execute("SHOW server_version")
            metadata["server_version"] = cursor.fetchone()[0]
            for table in ("portfolios", "accounts", "assets", "holdings", "trade_history", "crypto_holdings", "market_cache"):
                cursor.execute('SELECT count(*) FROM public.' + table)
                metadata["tables"][table] = cursor.fetchone()[0]
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (table,))
                metadata["columns"][table] = [r[0] for r in cursor.fetchall()]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("PG"):
            del env[key]
    for key, value in settings.items():
        mapping = {"host": "PGHOST", "port": "PGPORT", "user": "PGUSER", "password": "PGPASSWORD", "dbname": "PGDATABASE", "sslmode": "PGSSLMODE", "connect_timeout": "PGCONNECT_TIMEOUT", "options": "PGOPTIONS"}
        if key in mapping:
            env[mapping[key]] = str(value)
    archive = destination / "database.dump"
    with (destination / "pg_dump.log").open("wb") as log:
        subprocess.run([str(pg_dump), "--format=custom", "--no-password", "--lock-wait-timeout=10s", "--file=" + str(archive)], env=env, stdout=log, stderr=log, check=True)
    import hashlib
    metadata["archive_bytes"] = archive.stat().st_size
    with archive.open("rb") as stream:
        metadata["archive_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    (destination / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("Read-only backup completed:", destination.relative_to(ROOT))
    print("Server:", metadata["server_version"], "trade rows:", metadata["tables"]["trade_history"])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print connection exceptions or DSNs: these may contain secrets.
        print("Backup failed:", type(error).__name__)
        raise SystemExit(1)
