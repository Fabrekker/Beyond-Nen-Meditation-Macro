@echo off
setlocal
cd /d "%~dp0"
call "Start Macro.cmd" --update-only
exit /b %errorlevel%
