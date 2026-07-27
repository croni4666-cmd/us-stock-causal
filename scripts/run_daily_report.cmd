@echo off
REM scripts/run_daily_report.cmd
REM
REM Wrapper for Windows Task Scheduler (us-stock-causal P5-4)
REM
REM What it does:
REM   - cd to project root
REM   - run daily_report.py
REM   - capture stdout+stderr to output/logs/cron_<date>.log
REM   - passthrough exit code (P8 alert check uses it)
REM
REM Usage:
REM   scripts\run_daily_report.cmd
REM   scripts\run_daily_report.cmd --skip-fetch --skip-md
REM
REM Idempotent: log file overwritten each run
REM Encoding: ASCII only (so cmd / PowerShell both handle it cleanly)

setlocal

REM resolve project root: strip trailing \ from %~dp0, add \.., then absolute
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "PROJECT_ROOT=%PROJECT_ROOT%\.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

REM date in YYYY-MM-DD (PowerShell is more reliable than wmic + substr)
for /f "delims=" %%D in ('powershell -NoProfile -Command "(Get-Date -Format 'yyyy-MM-dd')"') do set "TODAY=%%D"

set "LOG_DIR=%PROJECT_ROOT%\output\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\cron_%TODAY%.log"

echo === us-stock-causal daily report === > "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo CWD:   %PROJECT_ROOT% >> "%LOG_FILE%"
echo Args:  %* >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

pushd "%PROJECT_ROOT%"
python examples\daily_report.py %* >> "%LOG_FILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
popd

echo. >> "%LOG_FILE%"
echo End:   %date% %time% >> "%LOG_FILE%"
echo Exit:  %EXITCODE% >> "%LOG_FILE%"

exit /b %EXITCODE%
