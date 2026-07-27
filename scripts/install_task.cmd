@echo off
REM scripts/install_task.cmd
REM
REM Register Windows Task Scheduler (us-stock-causal P5-4)
REM Run as admin: right-click cmd.exe - Run as administrator
REM
REM Usage:
REM   cd "G:\Minimax trade market\us-stock-causal"
REM   scripts\install_task.cmd          [default 17:00]
REM   scripts\install_task.cmd 16:30    [custom time]
REM
REM Idempotent: /F overwrites existing task
REM Requires admin: schtasks /Create fails with "Access is denied" otherwise
REM
REM Uninstall: schtasks /Delete /TN "us-stock-causal-daily-report" /F
REM Encoding: ASCII only (so cmd / PowerShell both handle it cleanly)

setlocal

REM resolve project root same as run_daily_report.cmd
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "PROJECT_ROOT=%PROJECT_ROOT%\.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

set "RUN_AT=%~1"
if "%RUN_AT%"=="" set "RUN_AT=17:00"

set "TASK_NAME=us-stock-causal-daily-report"
set "CMD_PATH=%PROJECT_ROOT%\scripts\run_daily_report.cmd"

echo === Install Windows Task: %TASK_NAME% ===
echo   Time:        %RUN_AT% (every day)
echo   Cmd:         %CMD_PATH%
echo   WorkingDir:  %PROJECT_ROOT%
echo.

REM schtasks /TR format: outer quotes wrap the whole command, path with spaces fine inside
schtasks /Create /SC DAILY /TN "%TASK_NAME%" /TR "\"%CMD_PATH%\"" /ST %RUN_AT% /F
if errorlevel 1 goto :install_failed

echo.
echo [OK] task registered
echo.
echo Verify:
echo   schtasks /Query /TN "%TASK_NAME%"
echo   schtasks /Run /TN "%TASK_NAME%"
echo.
echo Log:    %PROJECT_ROOT%\output\logs\cron_YYYY-MM-DD.log
echo Manual: scripts\run_daily_report.cmd
echo Uninstall: schtasks /Delete /TN "%TASK_NAME%" /F
goto :post_install

:install_failed
echo.
echo [FAIL] schtasks failed. Common causes:
echo   1. Not admin: right-click cmd.exe - Run as administrator
echo   2. Bad time format: HH:MM 24h (e.g. 17:00)

:post_install
exit /b 0
