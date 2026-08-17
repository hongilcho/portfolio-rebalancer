@echo off
echo ========================================================
echo   Starting Portfolio Rebalancer (FastAPI + React)
echo ========================================================

start cmd /k "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2 /nobreak >nul
start cmd /k "cd frontend && npm run dev"

echo.
echo Backend API : http://localhost:8000/docs
echo Frontend Web: http://localhost:5173
echo ========================================================
