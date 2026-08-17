from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.config import APP_PASSWORD

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    password: str

@router.post("/verify")
def verify_password(req: LoginRequest):
    if not APP_PASSWORD or req.password == APP_PASSWORD:
        return {"success": True, "message": "인증 성공"}
    raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다.")
