@echo off
setlocal
REM Dorian Lyrics Maker v1 double-click launcher for Windows
REM Delegates to PowerShell script with execution policy bypass

set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_croonify.ps1"
if %ERRORLEVEL% NEQ 0 (
  echo Failed to run Dorian Lyrics Maker v1. Ensure PowerShell allows scripts and Python 3 is installed.
  pause
)
endlocal