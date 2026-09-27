@echo off
cd /d "%~dp0"

echo ========================================================
echo   Starting Portfolio Rebalancer
echo ========================================================
echo.
echo [1/2] Starting Backend (FastAPI on Port 8000)...
start "Portfolio-Backend" cmd /k "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo [2/2] Starting Frontend (React on Port 5173)...
start "Portfolio-Frontend" /d "%~dp0frontend" cmd /k "npm run dev"

timeout /t 2 /nobreak >nul

echo.
echo ========================================================
echo   Servers started successfully!
echo.
echo   - Web App URL  : http://localhost:5173
echo   - Backend API  : http://localhost:8000/docs
echo ========================================================
echo.
echo Opening browser: http://localhost:5173
start http://localhost:5173

pause
