@echo off
REM scripts/install_all_tasks.cmd
REM
REM Register all 3 Windows Task Scheduler tasks (us-stock-causal v0.9.5)
REM Run as admin: right-click cmd.exe - Run as administrator
REM
REM Tasks created:
REM   1. us-stock-causal-daily-report             17:00 daily  (P5-4 main)
REM   2. us-stock-causal-daily-report-1705-backup 17:05 daily  (KI-3 Modern Standby guard)
REM   3. us-stock-causal-sec-filings-1730         17:30 daily  (Kansoku 借鉴 #1, A 方案)
REM
REM Usage:
REM   cd "G:\Minimax trade market\us-stock-causal"
REM   scripts\install_all_tasks.cmd
REM
REM Idempotent: /F overwrites existing tasks
REM Requires admin: schtasks /Create fails with "Access is denied" otherwise
REM
REM Uninstall: schtasks /Delete /TN "<task-name>" /F  (3 tasks)
REM Encoding: ASCII only (so cmd / PowerShell both handle it cleanly)

setlocal

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "PROJECT_ROOT=%PROJECT_ROOT%\.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

echo === Install Windows Tasks (us-stock-causal v0.9.5) ===
echo   Project:  %PROJECT_ROOT%
echo.

REM --- Task 1: 17:00 daily report (P5-4) ---
set "T1=us-stock-causal-daily-report"
set "T1_TIME=17:00"
set "T1_CMD=%PROJECT_ROOT%\scripts\run_daily_report.cmd"
echo [1/3] %T1%  at %T1_TIME%  daily
schtasks /Create /SC DAILY /TN "%T1%" /TR "\"%T1_CMD%\"" /ST %T1_TIME% /F
if errorlevel 1 goto :install_failed
echo       [OK]
echo.

REM --- Task 2: 17:05 backup (KI-3 Modern Standby guard) ---
set "T2=us-stock-causal-daily-report-1705-backup"
set "T2_TIME=17:05"
set "T2_CMD=%PROJECT_ROOT%\scripts\run_daily_report.cmd"
echo [2/3] %T2%  at %T2_TIME%  daily  (KI-3 guard)
schtasks /Create /SC DAILY /TN "%T2%" /TR "\"%T2_CMD%\"" /ST %T2_TIME% /F
if errorlevel 1 goto :install_failed
echo       [OK]
echo.

REM --- Task 3: 17:30 SEC EDGAR (Kansoku 借鉴 #1, A 方案) ---
set "T3=us-stock-causal-sec-filings-1730"
set "T3_TIME=17:30"
set "T3_CMD=%PROJECT_ROOT%\scripts\run_sec_filings_report.cmd"
echo [3/3] %T3%  at %T3_TIME%  daily  (SEC EDGAR cache)
schtasks /Create /SC DAILY /TN "%T3%" /TR "\"%T3_CMD%\"" /ST %T3_TIME% /F
if errorlevel 1 goto :install_failed
echo       [OK]
echo.

echo === All 3 tasks registered ===
echo.
echo Verify:
echo   schtasks /Query /TN "%T1%"
echo   schtasks /Query /TN "%T2%"
echo   schtasks /Query /TN "%T3%"
echo.
echo Logs:
echo   %PROJECT_ROOT%\output\logs\cron_YYYY-MM-DD.log         (17:00 + 17:05)
echo   %PROJECT_ROOT%\output\logs\sec_filings_YYYY-MM-DD.log  (17:30)
echo.
echo Uninstall (3 separate commands):
echo   schtasks /Delete /TN "%T1%" /F
echo   schtasks /Delete /TN "%T2%" /F
echo   schtasks /Delete /TN "%T3%" /F
goto :post_install

:install_failed
echo.
echo [FAIL] schtasks failed. Common causes:
echo   1. Not admin: right-click cmd.exe - Run as administrator
echo   2. Bad time format: HH:MM 24h (e.g. 17:00)

:post_install
exit /b 0
