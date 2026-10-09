"""Password login issues a signed, expiring single-owner API session."""
import hmac
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from backend import config
from backend.security import issue_session, login_limiter, validate_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


@router.post("/verify")
def verify_password(req: LoginRequest, request: Request, response: Response):
    validate_settings()
    login_limiter.check(request.client.host if request.client else "unknown")
    if not hmac.compare_digest(req.password.encode(), config.APP_PASSWORD.encode()):
        raise HTTPException(401, detail="비밀번호가 일치하지 않습니다.")
    response.headers["Cache-Control"] = "no-store"
    return issue_session()
