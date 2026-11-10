@echo off
setlocal
cd /d "%~dp0"
set "MACRO_PY="
if not exist local-python.txt goto system_python
set /p "MACRO_PY=" < local-python.txt
if exist "%MACRO_PY%" goto launch
:system_python
py -3.12 bootstrap.py --update-only
goto done
:launch
"%MACRO_PY%" bootstrap.py --update-only
:done
pause
