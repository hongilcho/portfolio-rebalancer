"""
사용자 인증 API 라우터 (Auth Router)
=====================================
웹 애플리케이션 진입 시 관리자 비밀번호 일치 여부를 검증합니다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.config import APP_PASSWORD

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    """비밀번호 검증 요청 모델"""
    password: str

@router.post("/verify")
def verify_password(req: LoginRequest):
    """
    클라이언트가 전송한 비밀번호를 환경변수(APP_PASSWORD)와 대조하여 인증 성공 여부를 반환합니다.
    """
    if not APP_PASSWORD or req.password == APP_PASSWORD:
        return {"success": True, "message": "인증 성공"}
    raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다.")
