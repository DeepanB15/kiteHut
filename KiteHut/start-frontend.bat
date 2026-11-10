@echo off
title RepoLens Frontend
cd /d "%~dp0frontend"
echo.
echo  ====================================
echo   RepoLens Frontend - Starting...
echo   Port: 5173
echo   URL:  http://localhost:5173
echo  ====================================
echo.
npm run dev
