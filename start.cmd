@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || goto :error
)
".venv\Scripts\python.exe" "scripts\setup.py" %*
set "rc=%errorlevel%"

REM keep the window open when the script was double-clicked from Explorer
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 (
  echo.
  echo Press any key to close this window...
  pause >nul
)
exit /b %rc%

:error
echo.
echo Could not create the venv - install Python 3.10+ and make sure it is on PATH.
pause
exit /b 1


