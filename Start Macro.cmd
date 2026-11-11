@echo off
setlocal
cd /d "%~dp0"
if not exist bootstrap.py goto incomplete
set "MACRO_PY="
if not exist local-python.txt goto try_launcher
set /p "MACRO_PY=" < local-python.txt
if not exist "%MACRO_PY%" goto try_launcher
"%MACRO_PY%" -c "import sys,struct;sys.exit(not(sys.version_info[:2]==(3,12) and struct.calcsize('P')==8))" >nul 2>nul
if errorlevel 1 goto try_launcher
"%MACRO_PY%" bootstrap.py %*
goto done
:try_launcher
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -c "import sys,struct;sys.exit(not(sys.version_info[:2]==(3,12) and struct.calcsize('P')==8))" >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 bootstrap.py %*
goto done
:try_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python -c "import sys,struct;sys.exit(not(sys.version_info[:2]==(3,12) and struct.calcsize('P')==8))" >nul 2>nul
if errorlevel 1 goto missing_python
python bootstrap.py %*
goto done
:missing_python
echo Python 3.12 ^(64-bit^) was not found. Installing another Python version alone is not enough.
echo Install Python 3.12 for Windows with pip, Tcl/Tk and the Python launcher enabled.
echo https://www.python.org/downloads/release/python-31210/
>> LOGS.jsonl echo {"event":"launcher_error","error":"Python 3.12 64-bit was not found."}
goto failed
:incomplete
echo Extract the ENTIRE macro ZIP to a folder before running Start Macro.cmd.
echo Keep the launcher and all Python files together. Do not run from inside the ZIP.
goto failed
:done
if "%errorlevel%"=="0" exit /b 0
echo.
echo The macro could not start. Read the error above before closing this window.
echo Setup and application failures are saved locally in LOGS.jsonl.
:failed
pause
exit /b 1
