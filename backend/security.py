"""Single-owner API sessions. No database or external IO."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import OrderedDict, deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from itsdangerous import BadData, URLSafeTimedSerializer
from starlette.responses import JSONResponse
from backend import config

SESSION_SECONDS = 12 * 60 * 60
PUBLIC_ENDPOINTS = {("POST", "/api/auth/verify"), ("GET", "/api/health"), ("HEAD", "/api/health")}


def validate_settings():
    if not config.APP_PASSWORD or not config.APP_PASSWORD.strip():
        raise RuntimeError("APP_PASSWORD is required; authentication cannot be disabled.")
    secret = config.APP_SESSION_SECRET
    if len(secret.strip()) < 32 or secret == config.APP_PASSWORD:
        raise RuntimeError("APP_SESSION_SECRET must be a separate random secret of at least 32 characters.")


def cors_origins():
    configured = os.getenv("APP_ALLOWED_ORIGINS")
    origins = configured.split(",") if configured is not None else ["https://portfolio-rebalancer-lemon.vercel.app"]
    if configured is None and not os.getenv("RENDER"):
        origins += [f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in range(5173, 5200)]
    result = []
    for origin in origins:
        origin = origin.strip().rstrip("/")
        parsed = urlsplit(origin)
        local = parsed.hostname in ("localhost", "127.0.0.1")
        if (not parsed.hostname or "*" in origin or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path or parsed.scheme not in ("http", "https")
                or (parsed.scheme == "http" and not local)):
            raise RuntimeError("APP_ALLOWED_ORIGINS must contain explicit HTTPS origins (or local development origins).")
        result.append(origin)
    if not result:
        raise RuntimeError("At least one allowed frontend origin is required.")
    return list(dict.fromkeys(result))


def serializer():
    validate_settings()
    return URLSafeTimedSerializer(config.APP_SESSION_SECRET, salt="portfolio-owner-session-v1",
                                  signer_kwargs={"digest_method": hashlib.sha256})


def credential_revision():
    return hmac.new(config.APP_SESSION_SECRET.encode(), config.APP_PASSWORD.encode(), hashlib.sha256).hexdigest()


def issue_session():
    expires = int(time.time()) + SESSION_SECONDS
    token = serializer().dumps({"v": 1, "sub": "owner", "revision": credential_revision(),
                                "expires": expires, "nonce": secrets.token_hex(16)})
    return {"success": True, "access_token": token, "token_type": "bearer", "expires_at": expires}


def verify_token(token):
    if not token or len(token) > 2048:
        raise HTTPException(401, "로그인이 필요합니다.", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = serializer().loads(token, max_age=SESSION_SECONDS)
        valid = (isinstance(payload, dict) and payload.get("v") == 1 and payload.get("sub") == "owner"
                 and type(payload.get("expires")) is int and payload["expires"] > time.time()
                 and isinstance(payload.get("revision"), str)
                 and hmac.compare_digest(payload["revision"], credential_revision()))
        if not valid:
            raise BadData("Invalid session")
    except BadData:
        raise HTTPException(401, "로그인이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.",
                            headers={"WWW-Authenticate": "Bearer"}) from None
    return payload


def require_session(request: Request):
    authorization = request.headers.get("authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(401, "로그인이 필요합니다.", headers={"WWW-Authenticate": "Bearer"})
    return verify_token(parts[1])


class ApiAuthenticationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (scope["method"], scope["path"]) not in PUBLIC_ENDPOINTS:
            try:
                require_session(Request(scope))
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
                response.headers["Cache-Control"] = "no-store"
                await response(scope, receive, send)
                return
        async def no_store(message):
            if scope["type"] == "http" and message["type"] == "http.response.start":
                message["headers"] = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)
        await self.app(scope, receive, no_store)


class LoginLimiter:
    """Bounded per-process limiter; proxy headers are not parsed here."""
    def __init__(self):
        self.lock = threading.Lock()
        self.global_attempts = deque()
        self.clients = OrderedDict()

    def check(self, host):
        now = time.monotonic()
        with self.lock:
            while self.global_attempts and self.global_attempts[0] <= now - 300:
                self.global_attempts.popleft()
            attempts = self.clients.setdefault(host, deque())
            self.clients.move_to_end(host)
            while len(self.clients) > 256:
                self.clients.popitem(last=False)
            while attempts and attempts[0] <= now - 300:
                attempts.popleft()
            if len(attempts) >= 10 or len(self.global_attempts) >= 120:
                raise HTTPException(429, "로그인 시도가 많습니다. 5분 뒤 다시 시도해주세요.",
                                    headers={"Retry-After": "300"})
            attempts.append(now)
            self.global_attempts.append(now)


login_limiter = LoginLimiter()
