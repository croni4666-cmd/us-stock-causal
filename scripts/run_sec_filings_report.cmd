@echo off
REM scripts/run_sec_filings_report.cmd
REM
REM Wrapper for Windows Task Scheduler (us-stock-causal SEC EDGAR 17:30 cron)
REM
REM What it does:
REM   - cd to project root
REM   - run sec_filings_report.py (33 ticker × 4 quarter × 0.5s/req = ~90s)
REM   - capture stdout+stderr to output/logs/sec_filings_<date>.log
REM   - passthrough exit code
REM
REM Usage:
REM   scripts\run_sec_filings_report.cmd
REM   scripts\run_sec_filings_report.cmd --ticker AAPL  (test single)
REM   scripts\run_sec_filings_report.cmd --sector XLK   (test single sector)
REM
REM Idempotent: log file overwritten each run
REM Encoding: ASCII only (so cmd / PowerShell both handle it cleanly)

setlocal

REM resolve project root
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "PROJECT_ROOT=%PROJECT_ROOT%\.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

REM date in YYYY-MM-DD
for /f "delims=" %%D in ('powershell -NoProfile -Command "(Get-Date -Format 'yyyy-MM-dd')"') do set "TODAY=%%D"

set "LOG_DIR=%PROJECT_ROOT%\output\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\sec_filings_%TODAY%.log"

echo === us-stock-causal SEC EDGAR Shadow mode === > "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo CWD:   %PROJECT_ROOT% >> "%LOG_FILE%"
echo Args:  %* >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

pushd "%PROJECT_ROOT%"
python examples\sec_filings_report.py %* >> "%LOG_FILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
popd

echo. >> "%LOG_FILE%"
echo End:   %date% %time% >> "%LOG_FILE%"
echo Exit:  %EXITCODE% >> "%LOG_FILE%"

exit /b %EXITCODE%
