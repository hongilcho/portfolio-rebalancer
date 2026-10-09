"""Real app routes, synthetic stores, and no real IO."""
import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend import config, security
from backend.main import app
from backend.routers import accounts, market, portfolios, trades


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(security, "login_limiter", security.LoginLimiter())
    from backend.routers import auth
    monkeypatch.setattr(auth, "login_limiter", security.LoginLimiter())
    return TestClient(app)


def headers():
    return {"Authorization": "Bearer " + security.issue_session()["access_token"]}


def test_every_registered_data_operation_requires_authentication(client):
    paths = app.openapi()["paths"]
    count = 0
    for path, methods in paths.items():
        for method in methods:
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if (method.upper(), path) in security.PUBLIC_ENDPOINTS:
                continue
            import re
            concrete = re.sub(r"{[^}]+}", "synthetic", path)
            response = client.request(method, concrete)
            assert response.status_code == 401, (method, path)
            assert response.headers["Cache-Control"] == "no-store"
            count += 1
    assert count >= 60


def test_health_survives_without_auth_and_documentation_is_not_public(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/docs").status_code == 401
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/docs", headers=headers()).status_code == 404


def test_login_issues_expiring_session_and_never_reflects_password(client):
    wrong = client.post("/api/auth/verify", json={"password": "wrong-sensitive-synthetic"})
    assert wrong.status_code == 401
    assert "wrong-sensitive-synthetic" not in wrong.text
    result = client.post("/api/auth/verify", json={"password": config.APP_PASSWORD})
    assert result.status_code == 200
    assert result.headers["Cache-Control"] == "no-store"
    payload = result.json()
    assert payload["expires_at"] > 0 and payload["token_type"] == "bearer"
    assert config.APP_PASSWORD not in payload["access_token"]
    assert security.verify_token(payload["access_token"])["sub"] == "owner"
    invalid = client.post("/api/auth/verify", json={"password": "sensitive-" * 200})
    assert invalid.status_code == 422 and "sensitive-" not in invalid.text


def test_missing_tampered_query_and_wrong_scheme_tokens_cannot_reach_data(client, monkeypatch):
    read = monkeypatch.setattr
    from unittest.mock import Mock
    store = Mock(return_value=[])
    read(accounts, "get_all_accounts", store)
    token = security.issue_session()["access_token"]
    for extra in ({}, {"Authorization": "Bearer " + token + "x"},
                  {"Authorization": "Basic " + token}, {"Authorization": "Bearer invalid"}):
        assert client.get("/api/accounts/?access_token="+token, headers=extra).status_code == 401
    store.assert_not_called()


def test_valid_session_keeps_crud_and_zip_export_working(client, monkeypatch):
    monkeypatch.setattr(accounts, "get_all_accounts", lambda **kw: [{"id": "synthetic"}])
    monkeypatch.setattr(portfolios, "create_portfolio", lambda *a: (True, "synthetic", {"id": "qa"}))
    monkeypatch.setattr(accounts, "update_account_limit_exhausted", lambda *a: (True, "synthetic"))
    monkeypatch.setattr(trades, "delete_trades", lambda *a: (True, "synthetic"))
    auth = headers()
    assert client.get("/api/accounts/", headers=auth).json()["accounts"][0]["id"] == "synthetic"
    assert client.post("/api/portfolios/", json={"name": "QA"}, headers=auth).status_code == 200
    assert client.put("/api/accounts/synthetic/toggle-exhaust", json={"is_exhausted": True}, headers=auth).status_code == 200
    assert client.request("DELETE", "/api/trades/batch", json={"trade_ids": ["qa"]}, headers=auth).status_code == 200
    for name in ("get_all_accounts", "get_all_assets", "get_all_holdings", "get_trade_history", "get_usd_ledgers", "get_usd_events"):
        monkeypatch.setattr(market, name, lambda: [])
    response = client.get("/api/market/export-csv", headers=auth)
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert response.content.startswith(b"PK")


def test_expiry_password_rotation_secret_rotation_and_foreign_payload(monkeypatch):
    now = 1800000000
    monkeypatch.setattr(security.time, "time", lambda: now)
    token = security.issue_session()["access_token"]
    now += security.SESSION_SECONDS + 1
    with pytest.raises(Exception) as result:
        security.verify_token(token)
    assert result.value.status_code == 401
    now -= security.SESSION_SECONDS + 1
    monkeypatch.setattr(config, "APP_PASSWORD", "new-synthetic-password")
    with pytest.raises(Exception) as result:
        security.verify_token(token)
    assert result.value.status_code == 401
    token = security.issue_session()["access_token"]
    monkeypatch.setattr(config, "APP_SESSION_SECRET", "rotated-synthetic-secret-more-than-32")
    with pytest.raises(Exception) as result:
        security.verify_token(token)
    assert result.value.status_code == 401
    forged = security.serializer().dumps({"v": 1, "sub": "admin"})
    with pytest.raises(Exception) as result:
        security.verify_token(forged)
    assert result.value.status_code == 401


def test_missing_credentials_fail_before_database_startup(monkeypatch):
    from unittest.mock import Mock
    import backend.main as main
    init = Mock()
    monkeypatch.setattr(main, "init_db", init)
    monkeypatch.setattr(config, "APP_SESSION_SECRET", "")
    with pytest.raises(RuntimeError, match="APP_SESSION_SECRET"):
        with TestClient(app):
            pass
    init.assert_not_called()
    monkeypatch.setattr(config, "APP_PASSWORD", "")
    with pytest.raises(RuntimeError, match="APP_PASSWORD"):
        security.validate_settings()


def test_cors_preflight_is_allowed_only_for_explicit_origin(client):
    request = {"Origin": "https://portfolio-rebalancer-lemon.vercel.app",
               "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
    response = client.options("/api/trades/batch", headers=request)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == request["Origin"]
    assert "access-control-allow-credentials" not in response.headers
    request["Origin"] = "https://untrusted.example"
    response = client.options("/api/trades/batch", headers=request)
    assert response.status_code == 400 and "access-control-allow-origin" not in response.headers


def test_login_rate_limit_and_bounded_memory(client):
    statuses = [client.post("/api/auth/verify", json={"password": "wrong"}).status_code for _ in range(11)]
    assert statuses[-1] == 429
    limiter = security.LoginLimiter()
    for i in range(600):
        try:
            limiter.check(str(i))
        except Exception:
            pass
    assert len(limiter.clients) <= 256


def test_security_opt_in_and_exact_table_inventory(monkeypatch):
    from unittest.mock import Mock
    from data.security_schema import APP_TABLES, SECURITY_SQL, initialize
    declared = set()
    import re
    for path in ("data/schema.py", "data/usd_schema.py", "data/workflow_schema.py"):
        for node in ast.walk(ast.parse(Path(path).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                declared.update(re.findall(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", node.value, re.I))
    assert set(APP_TABLES) == declared
    cursor = Mock()
    monkeypatch.setenv("PORTFOLIO_DB_SECURITY_ENABLED", "0")
    initialize(cursor)
    cursor.execute.assert_not_called()
    monkeypatch.setenv("PORTFOLIO_DB_SECURITY_ENABLED", "1")
    initialize(cursor)
    cursor.execute.assert_called_once_with(SECURITY_SQL)
    assert SECURITY_SQL in Path("migrations/security/20261009_apply.sql").read_text(encoding="utf-8")
    assert "CREATE POLICY" not in SECURITY_SQL.upper()


def test_wildcard_origins_rejected(monkeypatch):
    monkeypatch.setenv("APP_ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        security.cors_origins()


def test_configuration_has_no_password_fallback_and_rejects_whitespace(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert config.load_config()[1] == ""
    monkeypatch.setattr(config, "APP_PASSWORD", "   ")
    with pytest.raises(RuntimeError, match="APP_PASSWORD"):
        security.validate_settings()
    monkeypatch.setattr(config, "APP_PASSWORD", "synthetic")
    monkeypatch.setattr(config, "APP_SESSION_SECRET", " " * 40)
    with pytest.raises(RuntimeError, match="APP_SESSION_SECRET"):
        security.validate_settings()
