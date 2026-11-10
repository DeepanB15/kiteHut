@echo off
title RepoLens Backend
cd /d "%~dp0backend"
call .venv\Scripts\activate.bat
echo.
echo  ====================================
echo   RepoLens Backend - Starting...
echo   Port: 8000
echo   URL:  http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo  ====================================
echo.
uvicorn app.main:app --reload --port 8000
