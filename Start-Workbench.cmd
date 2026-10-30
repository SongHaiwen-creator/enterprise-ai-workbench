@echo off
setlocal
title Enterprise AI Workbench
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-workbench.ps1" %*
if errorlevel 1 (
  echo.
  echo Startup failed. Read the message above before closing this window.
  pause
  exit /b 1
)
endlocal
