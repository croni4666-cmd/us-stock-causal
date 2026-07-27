# scripts/setup_windows_task.ps1
#
# 注册 Windows Task Scheduler, 每天 17:00 跑 daily_report (us-stock-causal P5-4)
#
# 幂等: 重复跑 OK, 任务存在就 update
# 卸载: powershell -File scripts/setup_windows_task.ps1 -Uninstall
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File scripts/setup_windows_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/setup_windows_task.ps1 -Time "16:30"
#   powershell -ExecutionPolicy Bypass -File scripts/setup_windows_task.ps1 -Uninstall
#
# 设计:
# - 用 .cmd wrapper (run_daily_report.cmd) 而不是直接调 python, 这样 log 捕获稳
# - WorkingDirectory = 项目根, 这样相对路径 (examples/, output/) 正确
# - StartWhenAvailable = 错过的任务下次开机跑 (笔记本经常 sleep)
# - ExecutionTimeLimit = 2h (7 步 pipeline 最慢场景)
# - RestartCount = 3, RestartInterval = 5min (yfinance 限流临时失败 retry)

[CmdletBinding()]
param(
    [string]$Time = "17:00",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

# 项目根 (此 ps1 在 scripts/, 上一级)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CmdPath = Join-Path $ProjectRoot "scripts\run_daily_report.cmd"

$TaskName = "us-stock-causal-daily-report"
$TaskDescription = "us-stock-causal v3 - 每日 17:00 跑 7 步 pipeline (fetch/attribution/regression/md/html/dashboard/alerts)"

# ASCII-only 输出 (避免 Windows GBK 控制台乱码)
function Log([string]$msg) {
    Write-Host $msg
}

# --- Uninstall 模式 ---
if ($Uninstall) {
    Log "=== Uninstall $TaskName ==="
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Log "  [OK] 任务已删除"
    } else {
        Log "  [SKIP] 任务不存在, 不用删"
    }
    Log ""
    Log "  验证: Get-ScheduledTask -TaskName $TaskName"
    exit 0
}

# --- 验证时间格式 ---
if ($Time -notmatch "^\d{2}:\d{2}$") {
    Write-Error "时间格式错: '$Time' (要 HH:MM, e.g. 17:00)"
    exit 1
}

# --- 验证 .cmd 存在 ---
if (-not (Test-Path $CmdPath)) {
    Write-Error ".cmd wrapper 不存在: $CmdPath"
    Write-Error "  应该是: scripts/run_daily_report.cmd"
    exit 1
}

Log "=== Setup Windows Task: $TaskName ==="
Log "  Time:        $Time (每天)"
Log "  Cmd:         $CmdPath"
Log "  WorkingDir:  $ProjectRoot"
Log ""

# --- Action: 跑 .cmd wrapper ---
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$CmdPath`"" `
    -WorkingDirectory $ProjectRoot

# --- Trigger: 每天 $Time ---
$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $Time

# --- Settings: 容错 ---
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

# --- Principal: 当前用户, 交互式 (最稳, 不需要 SYSTEM) ---
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -RunLevel Limited `
    -LogonType S4U

# --- 注册 (Force 覆盖 = 幂等) ---
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $TaskDescription `
        -Force `
        -ErrorAction Stop
    Log "  [OK] 任务已注册/更新"
} catch {
    Write-Error "  [FAIL] 注册失败: $_"
    exit 1
}

Log ""
Log "=== Setup 完成 ==="
Log ""
Log "验证命令:"
Log "  Get-ScheduledTask -TaskName $TaskName"
Log "  Get-ScheduledTaskInfo -TaskName $TaskName"
Log ""
Log "日志路径:"
Log "  $ProjectRoot\output\logs\cron_<date>.log"
Log ""
Log "手动跑一次 (不等 17:00):"
Log "  Start-ScheduledTask -TaskName $TaskName"
Log ""
Log "禁用 (不删):"
Log "  Disable-ScheduledTask -TaskName $TaskName"
Log ""
Log "卸载 (删任务):"
Log "  powershell -ExecutionPolicy Bypass -File scripts\setup_windows_task.ps1 -Uninstall"
