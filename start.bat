@echo off
echo.
echo  =============================================
echo       REPOLENS - Starting All Services
echo  =============================================
echo.

:: Start Backend
echo [1/2] Starting Backend (port 8000)...
start "RepoLens Backend" cmd /k "cd /d "%~dp0backend" && call .venv\Scripts\activate.bat && echo. && echo  Backend running at http://localhost:8000 && echo  API Docs: http://localhost:8000/docs && echo. && uvicorn app.main:app --reload --port 8000"

:: Wait a moment for backend to start
timeout /t 2 /nobreak >nul

:: Start Frontend
echo [2/2] Starting Frontend (port 5173)...
start "RepoLens Frontend" cmd /k "cd /d "%~dp0frontend" && echo. && echo  Frontend running at http://localhost:5173 && echo. && npm run dev"

echo.
echo  =============================================
echo   All services started!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo  =============================================
echo.
echo  Close this window or press Ctrl+C to stop.
pause
