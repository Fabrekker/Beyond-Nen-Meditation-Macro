@echo off
setlocal
cd /d "%~dp0"
set "MACRO_PY="
if not exist local-python.txt goto system_python
set /p "MACRO_PY=" < local-python.txt
if exist "%MACRO_PY%" goto launch
:system_python
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 bootstrap.py
  goto done
)
echo Python was not found. Install Python 3.12 with the Python launcher, then reopen this file.
pause
exit /b 1
:launch
"%MACRO_PY%" bootstrap.py
:done
if errorlevel 1 pause
