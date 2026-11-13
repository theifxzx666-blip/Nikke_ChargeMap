@echo off
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopy

%PY% "%~dp0pages.py" %*
if errorlevel 1 (
  echo.
  echo [x] Launcher exited with an error. See the message above.
  pause
)
exit /b 0

:nopy
echo.
echo [x] Python 3 not found in PATH.
echo     Install Python 3, or edit this file and point PY at your python.exe
echo.
pause
exit /b 1
