@echo off
chcp 65001 >nul
title Portfolio Rebalancer Server Launcher

echo ========================================================
echo   [Portfolio Rebalancer] 서버 시작 스크립트
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/2] 백엔드(FastAPI) 서버를 시작합니다... (Port: 8000)
start "Portfolio Backend (FastAPI :8000)" cmd /k "chcp 65001 >nul && cd /d "%~dp0" && title [Backend] FastAPI Server (Port: 8000) && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo [2/2] 프론트엔드(React/Vite) 서버를 시작합니다... (Port: 5173)
start "Portfolio Frontend (Vite :5173)" cmd /k "chcp 65001 >nul && cd /d "%~dp0frontend" && title [Frontend] Vite Dev Server (Port: 5173) && npm run dev"

timeout /t 3 /nobreak >nul

echo.
echo ========================================================
echo   서버가 성공적으로 실행되었습니다!
echo.
echo   ▶ 웹 앱 접속 주소   : http://localhost:5173
echo   ▶ 백엔드 API 문서    : http://localhost:8000/docs
echo ========================================================
echo.
echo 기본 웹 브라우저에서 앱(http://localhost:5173)을 엽니다...
start http://localhost:5173

pause
